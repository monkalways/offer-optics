"""Compute Justin's reach/target/safety placement per program.

For each program in Tier 1-4 with >= 10 accepted reports in the applications
table, this tool computes:

  1. GPA percentile rank of Justin's projected top-6 midpoint (and low/high
     bounds) among accepted applicants.
  2. Out-of-province floor check: is Justin below the lowest OOP-accepted avg
     ever observed in this program? (Uses a tunable OOP-n threshold.)
  3. A GPA-only verdict band: safety / target / reach / hard_reach.
  4. A program-specific extracurricular (EC) weight, applied only to
     supplementary-application-driven programs. The EC bump can upgrade a
     verdict by one tier (never to safety from reach, which would be
     overconfident).
  5. A final verdict + explicit reasoning text so the dashboard can show
     *why* each verdict was assigned.

Outputs:
  - SQLite `placement` table (dropped + recreated on each run).
  - Per-program JSON files in .tmp/analysis/{program_key}.json.

Usage:
    python tools/analyze_program.py
    python tools/analyze_program.py --min-sample 5     # lower the sample cutoff
    python tools/analyze_program.py --print-summary    # just print existing rows
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / ".tmp" / "applications.sqlite"
PROFILE_PATH = PROJECT_ROOT / "config" / "justin_profile.json"
ANALYSIS_DIR = PROJECT_ROOT / ".tmp" / "analysis"


# ──────────────────────────────────────────────────────────────────────────────
# Program-specific EC weight
# ──────────────────────────────────────────────────────────────────────────────
# Only programs with a supplementary application / AIF give ECs real leverage.
# Everything else is academic-record-only for admission purposes.

EC_WEIGHT_PER_PROGRAM: dict[str, str] = {
    # Tier 1
    "mcmaster_bhsc":          "very_high",   # written supplementary app is the dominant signal
    "queens_bhsc":            "very_high",   # PSE: 1 written + 1 video response
    "waterloo_cs":            "medium",      # AIF is considered alongside (and below) raw GPA
    "uoft_lifesci_stgeorge":  "none",        # no supp app
    # Tier 2 — all academic-record-only
    "western_bmsc":           "none",
    "western_health_sci":     "none",
    "mcmaster_lifesci":       "none",
    "queens_lifesci":         "none",
    "uoft_lifesci_utm":       "none",
    "uoft_lifesci_utsc":      "none",
    "guelph_biomed":          "none",
    "ottawa_biomed":          "none",
    "brock_medsci":           "none",
    # Tier 3 (Waterloo backups) — all use the AIF
    "waterloo_cs_bba":        "medium",
    "waterloo_se":            "medium",
    "waterloo_math_cs":       "medium",
    "waterloo_math":          "medium",
}


# Verdict thresholds on GPA percentile within accepted population
def gpa_only_verdict(percentile: float | None) -> str:
    if percentile is None:
        return "insufficient_data"
    if percentile >= 65:
        return "safety"
    if percentile >= 35:
        return "target"
    if percentile >= 15:
        return "reach"
    return "hard_reach"


VERDICT_ORDER = ["hard_reach", "reach", "target", "safety"]


def upgrade_verdict(current: str, steps: int) -> str:
    if current == "insufficient_data" or steps <= 0:
        return current
    try:
        idx = VERDICT_ORDER.index(current)
    except ValueError:
        return current
    new_idx = min(idx + steps, len(VERDICT_ORDER) - 1)
    # Important: never upgrade to safety via ECs alone — the best we allow is
    # target (reach → target). Safety should require real GPA evidence.
    if VERDICT_ORDER[new_idx] == "safety" and current != "safety":
        return "target"
    return VERDICT_ORDER[new_idx]


# ──────────────────────────────────────────────────────────────────────────────
# Data extraction
# ──────────────────────────────────────────────────────────────────────────────

def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def connect_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found. Run tools/build_sqlite.py first.")
    return sqlite3.connect(DB_PATH)


def load_programs_in_scope(conn: sqlite3.Connection) -> list[dict]:
    """Return all programs that have an entry in the programs table."""
    cur = conn.execute("""
        SELECT program_key, tier, university, program
        FROM programs
        WHERE program_key IS NOT NULL
        ORDER BY tier, program_key
    """)
    return [
        {"program_key": r[0], "tier": r[1], "university": r[2], "program": r[3]}
        for r in cur.fetchall()
    ]


def compute_percentile(conn: sqlite3.Connection, program_key: str, avg: float
                       ) -> tuple[int, float | None]:
    """Return (n_accepted, percentile_of_avg). Percentile is the % of accepted
    applicants whose avg is <= `avg`. None if no accepted samples."""
    cur = conn.execute("""
        SELECT
            COUNT(*) AS n,
            SUM(CASE WHEN best_avg <= ? THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) AS pct
        FROM applications
        WHERE program_key = ?
          AND decision = 'accepted'
          AND best_avg IS NOT NULL
    """, (avg, program_key))
    n, pct = cur.fetchone()
    return int(n), (round(pct, 1) if pct is not None else None)


def compute_oop_stats(conn: sqlite3.Connection, program_key: str
                      ) -> tuple[int, float | None, float | None]:
    """Return (n_oop, oop_min, oop_mean) for accepted out-of-province applicants."""
    cur = conn.execute("""
        SELECT
            COUNT(*)             AS n,
            MIN(best_avg)        AS oop_min,
            AVG(best_avg)        AS oop_mean
        FROM applications
        WHERE program_key = ?
          AND decision = 'accepted'
          AND best_avg IS NOT NULL
          AND province IS NOT NULL
          AND LOWER(province) NOT LIKE '%ontario%'
    """, (program_key,))
    n, omin, omean = cur.fetchone()
    return (int(n),
            round(omin, 1) if omin is not None else None,
            round(omean, 1) if omean is not None else None)


def compute_median(conn: sqlite3.Connection, program_key: str) -> float | None:
    """Return the median accepted avg for the program."""
    cur = conn.execute("""
        WITH ranked AS (
            SELECT best_avg,
                   ROW_NUMBER() OVER (ORDER BY best_avg) AS rn,
                   COUNT(*)     OVER ()                   AS cnt
            FROM applications
            WHERE program_key = ? AND decision = 'accepted' AND best_avg IS NOT NULL
        )
        SELECT best_avg FROM ranked WHERE rn = MAX(1, (cnt + 1) / 2)
    """, (program_key,))
    row = cur.fetchone()
    return round(row[0], 1) if row and row[0] is not None else None


# ──────────────────────────────────────────────────────────────────────────────
# Reasoning + verdict
# ──────────────────────────────────────────────────────────────────────────────

VERDICT_LABELS = {
    "safety":       "Safety",
    "target":       "Target",
    "reach":        "Reach",
    "hard_reach":   "Hard Reach",
    "insufficient_data": "Insufficient data",
}


def build_reasoning(
    program_key: str,
    tier: int,
    university: str,
    program: str,
    n_accepted: int,
    justin_mid: float,
    justin_low: float,
    justin_high: float,
    pct_low: float | None,
    pct_mid: float | None,
    pct_high: float | None,
    median_avg: float | None,
    oop_n: int,
    oop_min: float | None,
    oop_mean: float | None,
    gpa_verdict: str,
    ec_weight: str,
    final_verdict: str,
    profile: dict,
) -> str:
    lines: list[str] = []

    if n_accepted < 10:
        lines.append(
            f"Only {n_accepted} accepted reports on record — sample too small for a reliable percentile. "
            f"Treat as insufficient data; rely on the official requirements and Justin's academic record directly."
        )
        return " ".join(lines)

    # 1. GPA percentile line
    median_str = f"{median_avg}" if median_avg is not None else "?"
    pct_mid_str = f"{pct_mid}" if pct_mid is not None else "?"
    pct_range_str = f"{pct_low}-{pct_high}" if pct_low is not None and pct_high is not None else pct_mid_str
    lines.append(
        f"Justin's projected top-6 midpoint of {justin_mid}% sits at the {pct_mid_str}th percentile "
        f"of accepted reports for {university} {program} "
        f"(n={n_accepted}, median accepted avg {median_str}%). "
        f"Projection range ({justin_low}-{justin_high}%) places him at the {pct_range_str}th percentile."
    )

    # 2. OOP signal
    # Distinguish two regimes: large enough sample to treat as a real floor
    # (n_oop >= 10), vs small sample which is directional only.
    OOP_DOWNGRADE_MIN_N = 10
    if oop_n >= 1 and oop_min is not None:
        if oop_n >= OOP_DOWNGRADE_MIN_N:
            # Large-enough sample: the observed OOP minimum carries weight.
            if justin_high < oop_min:
                lines.append(
                    f"Out-of-province floor: {oop_n} OOP-accepted reports across 4 cycles, "
                    f"all with averages >= {oop_min}%. Even Justin's HIGH projection of {justin_high}% "
                    f"is below this observed floor — strong evidence the OOP bar is meaningfully higher "
                    f"than in-province, and this drives the hard_reach framing."
                )
            elif justin_mid < oop_min:
                lines.append(
                    f"Out-of-province floor: {oop_n} OOP-accepted reports all above {oop_min}%. "
                    f"Justin's midpoint {justin_mid}% is below this floor; his high projection "
                    f"{justin_high}% clears it."
                )
            elif oop_mean is not None:
                lines.append(
                    f"Out-of-province subset (n={oop_n}): mean accepted {oop_mean}%, min {oop_min}%. "
                    f"No adverse OOP signal for Justin's projection range."
                )
        else:
            # Small sample: surface as directional only.
            if justin_high < oop_min:
                lines.append(
                    f"OOP DIRECTIONAL SIGNAL (small sample, treat with caution): only {oop_n} OOP-accepted "
                    f"reports across 4 cycles, all clustered above {oop_min}%. Even Justin's HIGH projection "
                    f"of {justin_high}% is below the observed OOP minimum, but with n={oop_n} this is a "
                    f"YELLOW FLAG, not a hard threshold — one additional data point could shift the floor "
                    f"by several percentage points. Suggests OOP bar may be tougher than in-province; do not "
                    f"let it override the percentile-based verdict."
                )
            elif justin_mid < oop_min:
                lines.append(
                    f"OOP DIRECTIONAL SIGNAL (small sample, n={oop_n}): mean accepted {oop_mean}%, "
                    f"min {oop_min}%. Justin's midpoint {justin_mid}% is below the observed OOP minimum "
                    f"but his high projection {justin_high}% clears it. Treat as directional only."
                )
            elif oop_mean is not None:
                lines.append(
                    f"OOP subset (small sample, n={oop_n}): mean accepted {oop_mean}%, min {oop_min}%. "
                    f"Justin's range is consistent with the observed OOP cluster."
                )

    # 3. EC leverage
    ec_strengths = profile.get("extracurriculars", {}).get("ec_strengths_by_target", {})
    program_ec_note = ec_strengths.get(program_key)

    if ec_weight == "very_high":
        if program_ec_note:
            lines.append(f"Supp-app leverage (very high weight at this program): {program_ec_note}")
        if final_verdict != gpa_verdict:
            lines.append(
                f"EC adjustment applied: GPA-only verdict would be {VERDICT_LABELS[gpa_verdict].upper()}, "
                f"upgraded to {VERDICT_LABELS[final_verdict].upper()} via strong supplementary-application leverage. "
                f"ECs alone never upgrade a reach to a safety — the upgrade is capped at target."
            )
    elif ec_weight == "medium":
        if program_ec_note:
            lines.append(f"AIF leverage (medium weight at this program): {program_ec_note}")
        if final_verdict != gpa_verdict:
            lines.append(
                f"EC adjustment applied: GPA-only verdict would be {VERDICT_LABELS[gpa_verdict].upper()}, "
                f"upgraded to {VERDICT_LABELS[final_verdict].upper()} via strong AIF content. "
                f"Note: Waterloo CS still weighs grades heavily and the AIF is a secondary signal."
            )
        else:
            lines.append(
                f"AIF content will be strong but does not change the grade-driven verdict of "
                f"{VERDICT_LABELS[final_verdict].upper()}."
            )
    else:
        # No supp app — ECs don't affect the decision
        lines.append(
            f"This program does not use a supplementary application; ECs do not affect the admission decision. "
            f"Verdict is driven entirely by GPA percentile."
        )

    # 4. Final verdict summary
    lines.append(f"FINAL VERDICT: {VERDICT_LABELS[final_verdict].upper()}.")

    # 5. Always-include self-selection caveat (brief)
    lines.append(
        "Caveat: Reddit dataset is heavily self-selected toward acceptances "
        "(~95-99% of reports are accepts), so percentiles are relative to admitted students, not raw applicant pools."
    )

    return " ".join(lines)


def verdict_confidence(n_accepted: int, oop_n: int, tier: int) -> str:
    """Rough confidence in the verdict given sample size."""
    if n_accepted < 10:
        return "insufficient"
    if n_accepted < 30 or (tier == 4):
        return "low"
    if n_accepted < 60:
        return "medium"
    return "high"


# ──────────────────────────────────────────────────────────────────────────────
# Per-program analysis
# ──────────────────────────────────────────────────────────────────────────────

def analyze_program(conn: sqlite3.Connection, prog: dict, profile: dict) -> dict:
    program_key = prog["program_key"]
    tier = prog["tier"]
    university = prog["university"]
    program_name = prog["program"]

    top6 = profile["grade_12_projected_top6_average"]
    justin_low = float(top6["low"])
    justin_mid = float(top6["midpoint"])
    justin_high = float(top6["high"])

    n_low, pct_low = compute_percentile(conn, program_key, justin_low)
    n_mid, pct_mid = compute_percentile(conn, program_key, justin_mid)
    n_high, pct_high = compute_percentile(conn, program_key, justin_high)
    # n should be identical for all three (same program) but keep guards anyway
    n_accepted = n_mid

    median_avg = compute_median(conn, program_key)
    oop_n, oop_min, oop_mean = compute_oop_stats(conn, program_key)

    # GPA-only verdict: use midpoint
    gpa_verdict = gpa_only_verdict(pct_mid)

    # Apply OOP floor downgrade ONLY when we have a statistically meaningful
    # OOP sample (n >= 10). With smaller samples (e.g. McMaster BHSc has only
    # 5 OOP reports across 4 cycles), the observed minimum is far too noisy
    # to override the percentile-based verdict — one more data point could
    # shift the "floor" by several percentage points. Low-sample OOP signals
    # are still surfaced in the reasoning text as *directional* warnings, but
    # they do not flip a reach into a hard_reach.
    OOP_DOWNGRADE_MIN_N = 10
    if oop_n >= OOP_DOWNGRADE_MIN_N and oop_min is not None and justin_high < oop_min:
        gpa_verdict = "hard_reach"

    # EC adjustment
    ec_weight = EC_WEIGHT_PER_PROGRAM.get(program_key, "none")

    # If the sample is too thin for a reliable verdict, force insufficient_data
    # regardless of what the percentile math produced.
    if n_accepted < 10:
        gpa_verdict = "insufficient_data"
        final_verdict = "insufficient_data"
    elif ec_weight == "very_high":
        # BHSc-style programs: the supplementary application is the dominant
        # signal. Strong ECs can upgrade one tier, but never past target.
        if gpa_verdict == "hard_reach":
            final_verdict = "reach"
        elif gpa_verdict == "reach":
            final_verdict = "target"
        else:
            final_verdict = gpa_verdict
    elif ec_weight == "medium":
        # Waterloo CS / SE / Math-CS: AIF is a real but secondary signal.
        # Can rescue a hard_reach to a reach, but a GPA-driven reach stays a
        # reach. The AIF will make the application strong but doesn't close
        # a material grade gap.
        if gpa_verdict == "hard_reach":
            final_verdict = "reach"
        else:
            final_verdict = gpa_verdict
    else:
        final_verdict = gpa_verdict

    reasoning = build_reasoning(
        program_key=program_key, tier=tier, university=university, program=program_name,
        n_accepted=n_accepted, justin_mid=justin_mid, justin_low=justin_low, justin_high=justin_high,
        pct_low=pct_low, pct_mid=pct_mid, pct_high=pct_high, median_avg=median_avg,
        oop_n=oop_n, oop_min=oop_min, oop_mean=oop_mean,
        gpa_verdict=gpa_verdict, ec_weight=ec_weight, final_verdict=final_verdict,
        profile=profile,
    )

    confidence = verdict_confidence(n_accepted, oop_n, tier or 99)

    return {
        "program_key": program_key,
        "tier": tier,
        "university": university,
        "program": program_name,
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "n_accepted": n_accepted,
        "median_accepted_avg": median_avg,
        "justin_mid": justin_mid,
        "justin_low": justin_low,
        "justin_high": justin_high,
        "gpa_percentile_low": pct_low,
        "gpa_percentile_mid": pct_mid,
        "gpa_percentile_high": pct_high,
        "oop_n": oop_n,
        "oop_min": oop_min,
        "oop_mean": oop_mean,
        "gpa_only_verdict": gpa_verdict,
        "ec_weight": ec_weight,
        "final_verdict": final_verdict,
        "final_verdict_label": VERDICT_LABELS[final_verdict],
        "reasoning": reasoning,
        "confidence": confidence,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Output writers
# ──────────────────────────────────────────────────────────────────────────────

def write_placement_table(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executescript("""
        DROP TABLE IF EXISTS placement;
        CREATE TABLE placement (
            program_key           TEXT PRIMARY KEY,
            tier                  INTEGER,
            university            TEXT,
            program               TEXT,
            analyzed_at           TEXT,
            n_accepted            INTEGER,
            median_accepted_avg   REAL,
            justin_mid            REAL,
            justin_low            REAL,
            justin_high           REAL,
            gpa_percentile_low    REAL,
            gpa_percentile_mid    REAL,
            gpa_percentile_high   REAL,
            oop_n                 INTEGER,
            oop_min               REAL,
            oop_mean              REAL,
            gpa_only_verdict      TEXT,
            ec_weight             TEXT,
            final_verdict         TEXT,
            final_verdict_label   TEXT,
            reasoning             TEXT,
            confidence            TEXT
        );
        CREATE INDEX idx_placement_tier ON placement(tier);
        CREATE INDEX idx_placement_verdict ON placement(final_verdict);
    """)
    cols = [
        "program_key", "tier", "university", "program", "analyzed_at",
        "n_accepted", "median_accepted_avg",
        "justin_mid", "justin_low", "justin_high",
        "gpa_percentile_low", "gpa_percentile_mid", "gpa_percentile_high",
        "oop_n", "oop_min", "oop_mean",
        "gpa_only_verdict", "ec_weight", "final_verdict", "final_verdict_label",
        "reasoning", "confidence",
    ]
    placeholders = ", ".join(":" + c for c in cols)
    col_list = ", ".join(cols)
    conn.executemany(
        f"INSERT INTO placement ({col_list}) VALUES ({placeholders})",
        rows,
    )
    conn.commit()


def write_json_files(rows: list[dict]) -> None:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    for row in rows:
        out_path = ANALYSIS_DIR / f"{row['program_key']}.json"
        out_path.write_text(
            json.dumps(row, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-sample", type=int, default=0,
                        help="Minimum n_accepted to emit a row (default 0 — all programs)")
    parser.add_argument("--print-summary", action="store_true",
                        help="Print existing placement rows from the DB and exit")
    args = parser.parse_args()

    if args.print_summary:
        conn = connect_db()
        try:
            rows = conn.execute("""
                SELECT tier, program_key, n_accepted, gpa_percentile_mid,
                       gpa_only_verdict, ec_weight, final_verdict_label, confidence
                FROM placement ORDER BY tier, program_key
            """).fetchall()
        finally:
            conn.close()
        if not rows:
            print("placement table is empty.")
            return 0
        print(f"{'tier':<5}{'program_key':<30}{'n':<5}{'pct':<6}{'gpa_only':<14}{'ec':<12}{'final':<20}{'conf':<10}")
        print("-" * 100)
        for r in rows:
            print(f"{r[0] or '?':<5}{r[1]:<30}{r[2]:<5}{r[3] or '?':<6}{r[4]:<14}{r[5]:<12}{r[6]:<20}{r[7]:<10}")
        return 0

    profile = load_profile()
    print(f"Analyzing placement for Justin ({profile['grade_12_projected_top6_average']['midpoint']}% midpoint)")

    conn = connect_db()
    try:
        programs = load_programs_in_scope(conn)
        print(f"  {len(programs)} programs in scope")

        rows: list[dict] = []
        for prog in programs:
            row = analyze_program(conn, prog, profile)
            if row["n_accepted"] < args.min_sample:
                continue
            rows.append(row)

        rows.sort(key=lambda r: (r["tier"] or 99, -(r["n_accepted"] or 0)))

        write_placement_table(conn, rows)
    finally:
        conn.close()

    write_json_files(rows)

    # Summary print
    print()
    print(f"{'tier':<5}{'program_key':<30}{'n':<5}{'pct':<6}{'gpa_only':<14}{'ec':<12}{'final':<20}{'conf':<13}")
    print("-" * 110)
    for r in rows:
        pct = r["gpa_percentile_mid"]
        pct_str = f"{pct:.0f}" if pct is not None else "?"
        print(f"{r['tier'] or '?':<5}{r['program_key']:<30}{r['n_accepted']:<5}"
              f"{pct_str:<6}{r['gpa_only_verdict']:<14}{r['ec_weight']:<12}"
              f"{r['final_verdict']:<20}{r['confidence']:<13}")

    print()
    print(f"Wrote placement table + {len(rows)} JSON files to .tmp/analysis/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
