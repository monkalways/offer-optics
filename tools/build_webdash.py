"""Build the data.json file consumed by the static web dashboard.

Reads from the same upstream artifacts as tools/build_dashboard.py:
  - .tmp/applications.sqlite (placement, requirements, applications, cycles)
  - .tmp/analysis/{program_key}.json (per-program reasoning text)
  - config/justin_profile.json
  - config/requirements.yaml

Writes:
  - docs/data.json — the single JSON the static page (docs/index.html) reads.

Usage:
    python tools/build_webdash.py
    python tools/build_webdash.py --print-summary
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / ".tmp" / "applications.sqlite"
PROFILE_PATH = PROJECT_ROOT / "config" / "justin_profile.json"
REQ_YAML_PATH = PROJECT_ROOT / "config" / "requirements.yaml"
ANALYSIS_DIR = PROJECT_ROOT / ".tmp" / "analysis"
DOCS_DIR = PROJECT_ROOT / "docs"
OUT_PATH = DOCS_DIR / "data.json"

# Justin's application cycle is 2026-2027 (G12 fall 2026 → entry fall 2027).
# The curated requirements.yaml uses the 2025-2026 cycle as a template; we shift
# every date by +1 year for the dashboard so the checklist reflects Justin's
# actual cycle. Add 365 days (close enough; OUAC dates rarely shift more than ±1).
JUSTIN_CYCLE_LABEL = "2026-2027"
DATE_SHIFT_DAYS = 365


# ──────────────────────────────────────────────────────────────────────────────
# I/O helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def load_requirements_yaml() -> dict:
    return yaml.safe_load(REQ_YAML_PATH.read_text(encoding="utf-8"))


def load_analysis_json(program_key: str) -> dict | None:
    path = ANALYSIS_DIR / f"{program_key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def shift_date(iso_date: str | None, days: int = DATE_SHIFT_DAYS) -> str | None:
    if not iso_date:
        return None
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d").date()
    except ValueError:
        return iso_date  # leave non-ISO strings alone
    return (dt + timedelta(days=days)).isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# SQLite queries
# ──────────────────────────────────────────────────────────────────────────────

def query_placement(conn: sqlite3.Connection) -> list[dict]:
    """All placement rows joined to programs metadata."""
    rows = conn.execute("""
        SELECT
            p.tier,
            p.program_key,
            p.program,
            p.university,
            p.median_accepted_avg,
            p.n_accepted,
            p.justin_mid,
            p.justin_low,
            p.justin_high,
            p.gpa_percentile_low,
            p.gpa_percentile_mid,
            p.gpa_percentile_high,
            p.oop_n,
            p.oop_min,
            p.oop_mean,
            p.gpa_only_verdict,
            p.ec_weight,
            p.final_verdict,
            p.final_verdict_label,
            p.confidence,
            p.reasoning
        FROM placement p
        ORDER BY p.tier,
            CASE p.final_verdict
                WHEN 'safety' THEN 1
                WHEN 'target' THEN 2
                WHEN 'reach' THEN 3
                WHEN 'hard_reach' THEN 4
                ELSE 5
            END,
            p.n_accepted DESC
    """).fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM placement LIMIT 0").description]
    cols_used = [
        "tier", "program_key", "program", "university",
        "median_accepted_avg", "n_accepted",
        "justin_mid", "justin_low", "justin_high",
        "gpa_percentile_low", "gpa_percentile_mid", "gpa_percentile_high",
        "oop_n", "oop_min", "oop_mean",
        "gpa_only_verdict", "ec_weight", "final_verdict", "final_verdict_label",
        "confidence", "reasoning",
    ]
    return [dict(zip(cols_used, r)) for r in rows]


def query_quartiles(conn: sqlite3.Connection, program_key: str) -> dict:
    """Return min/p25/p50/p75/max for accepted averages of one program."""
    rows = conn.execute("""
        WITH ranked AS (
            SELECT best_avg,
                   ROW_NUMBER() OVER (ORDER BY best_avg) AS rn,
                   COUNT(*)     OVER ()                  AS cnt
            FROM applications
            WHERE program_key = ? AND decision = 'accepted' AND best_avg IS NOT NULL
        )
        SELECT
            (SELECT MIN(best_avg) FROM ranked) AS min_v,
            (SELECT best_avg FROM ranked WHERE rn = MAX(1, (cnt + 2) / 4)  LIMIT 1) AS p25,
            (SELECT best_avg FROM ranked WHERE rn = MAX(1, (cnt + 1) / 2)  LIMIT 1) AS p50,
            (SELECT best_avg FROM ranked WHERE rn = MAX(1, (3 * cnt + 3) / 4) LIMIT 1) AS p75,
            (SELECT MAX(best_avg) FROM ranked) AS max_v
    """, (program_key,)).fetchone()
    if not rows:
        return {"min": None, "p25": None, "p50": None, "p75": None, "max": None}
    return {
        "min": round(rows[0], 1) if rows[0] is not None else None,
        "p25": round(rows[1], 1) if rows[1] is not None else None,
        "p50": round(rows[2], 1) if rows[2] is not None else None,
        "p75": round(rows[3], 1) if rows[3] is not None else None,
        "max": round(rows[4], 1) if rows[4] is not None else None,
    }


def query_histogram_bins(conn: sqlite3.Connection, program_key: str,
                         bin_lo: int = 70, bin_hi: int = 100) -> list[dict]:
    """Return histogram bins (1-percentage-point wide) of accepted averages."""
    rows = conn.execute("""
        SELECT CAST(FLOOR(best_avg) AS INTEGER) AS bin, COUNT(*) AS n
        FROM applications
        WHERE program_key = ? AND decision = 'accepted' AND best_avg IS NOT NULL
        GROUP BY bin
        ORDER BY bin
    """, (program_key,)).fetchall()
    counts = {int(b): int(n) for b, n in rows}
    return [{"bin": b, "n": counts.get(b, 0)} for b in range(bin_lo, bin_hi + 1)]


def query_requirements_for(conn: sqlite3.Connection, program_key: str) -> dict | None:
    row = conn.execute("""
        SELECT
            program_key, tier, source_url, confidence,
            application_deadline_ouac, application_deadline_supp, document_deadline,
            decision_release_window,
            supp_app_required, supp_app_type, supp_app_url, supp_app_notes,
            casper_required, casper_format,
            interview_required, interview_format,
            references_required, references_count,
            min_average_competitive, prereq_courses_json, prereq_notes,
            oop_eligible, oop_notes,
            application_fee_cad, notes
        FROM requirements WHERE program_key = ?
    """, (program_key,)).fetchone()
    if not row:
        return None
    cols = [
        "program_key", "tier", "source_url", "confidence",
        "deadline_ouac_template", "deadline_supp_template", "deadline_doc_template",
        "decision_window",
        "supp_app_required", "supp_app_type", "supp_app_url", "supp_app_notes",
        "casper_required", "casper_format",
        "interview_required", "interview_format",
        "references_required", "references_count",
        "min_average_competitive", "prereq_courses_json", "prereq_notes",
        "oop_eligible", "oop_notes",
        "fee_cad", "notes",
    ]
    d = dict(zip(cols, row))
    # Add Justin-cycle (2026-2027) shifted dates
    d["deadline_ouac"] = shift_date(d["deadline_ouac_template"])
    d["deadline_supp"] = shift_date(d["deadline_supp_template"])
    d["deadline_doc"] = shift_date(d["deadline_doc_template"])
    # Parse the JSON-encoded prereq list
    try:
        d["prereq_courses"] = json.loads(d.pop("prereq_courses_json") or "[]")
    except json.JSONDecodeError:
        d["prereq_courses"] = []
    # Coerce booleans (SQLite stores them as integers)
    for k in ("supp_app_required", "casper_required", "interview_required",
              "references_required", "oop_eligible"):
        if d.get(k) is not None:
            d[k] = bool(d[k])
    return d


def query_yoy_trends(conn: sqlite3.Connection) -> list[dict]:
    """Per-program (Tier 1) cycle-by-cycle accepted-avg mean/min/max."""
    rows = conn.execute("""
        SELECT
            p.program_key,
            p.program,
            a.cycle,
            COUNT(*)                 AS n,
            ROUND(AVG(a.best_avg), 1) AS mean_v,
            ROUND(MIN(a.best_avg), 1) AS min_v,
            ROUND(MAX(a.best_avg), 1) AS max_v
        FROM applications a
        JOIN programs p ON p.program_key = a.program_key
        WHERE p.tier = 1 AND a.decision = 'accepted' AND a.best_avg IS NOT NULL
        GROUP BY p.program_key, p.program, a.cycle
        ORDER BY p.program_key, a.cycle
    """).fetchall()
    by_program: dict[str, dict] = {}
    for program_key, program, cycle, n, mean_v, min_v, max_v in rows:
        if program_key not in by_program:
            by_program[program_key] = {"program_key": program_key, "program": program, "cycles": []}
        by_program[program_key]["cycles"].append({
            "cycle": cycle, "n": n, "mean": mean_v, "min": min_v, "max": max_v,
        })
    return list(by_program.values())


def query_decision_timeline(conn: sqlite3.Connection) -> list[dict]:
    """Per-program (Tier 1) month-by-month decision counts in the last complete cycle (24-25)."""
    rows = conn.execute("""
        SELECT
            p.program_key,
            p.program,
            SUBSTR(a.decision_date, 1, 7)  AS year_month,
            COUNT(*) AS n,
            SUM(CASE WHEN a.decision = 'accepted' THEN 1 ELSE 0 END) AS n_accepted,
            SUM(CASE WHEN a.decision = 'rejected' THEN 1 ELSE 0 END) AS n_rejected,
            SUM(CASE WHEN a.decision = 'deferred' THEN 1 ELSE 0 END) AS n_deferred
        FROM applications a
        JOIN programs p ON p.program_key = a.program_key
        WHERE p.tier = 1 AND a.cycle = '2024-2025' AND a.decision_date IS NOT NULL
        GROUP BY p.program_key, p.program, year_month
        ORDER BY p.program_key, year_month
    """).fetchall()
    by_program: dict[str, dict] = {}
    for program_key, program, year_month, n, n_accepted, n_rejected, n_deferred in rows:
        if program_key not in by_program:
            by_program[program_key] = {"program_key": program_key, "program": program, "months": []}
        by_program[program_key]["months"].append({
            "year_month": year_month,
            "n": n,
            "n_accepted": n_accepted,
            "n_rejected": n_rejected,
            "n_deferred": n_deferred,
        })
    return list(by_program.values())


def query_cycles(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT cycle, region, n_rows, n_decisions_mapped,
               n_universities_mapped, n_programs_mapped, live, refresh_until, fetched_at
        FROM cycles ORDER BY cycle
    """).fetchall()
    cols = ["cycle", "region", "n_rows", "n_decisions_mapped",
            "n_universities_mapped", "n_programs_mapped", "live", "refresh_until", "fetched_at"]
    return [dict(zip(cols, r)) for r in rows]


# ──────────────────────────────────────────────────────────────────────────────
# Program enrichment
# ──────────────────────────────────────────────────────────────────────────────

def build_program_object(placement_row: dict, conn: sqlite3.Connection,
                         profile: dict) -> dict:
    """Combine placement row + quartiles + requirements + reasoning + histogram
    into the per-program shape consumed by the frontend."""
    program_key = placement_row["program_key"]

    quartiles = query_quartiles(conn, program_key)
    requirements = query_requirements_for(conn, program_key) or {}
    histogram = query_histogram_bins(conn, program_key)

    # OOP caveat: surface ONLY when the small-sample OOP signal is adverse
    # (i.e. Justin's projection range is at or below the observed OOP minimum).
    # Non-adverse OOP signals are noise — hide them so the dashboard stays
    # focused on the real signal (McMaster BHSc's 97.8 floor vs Justin's 95.5).
    oop_n = placement_row.get("oop_n") or 0
    oop_min_v = placement_row.get("oop_min")
    justin_mid_v = placement_row.get("justin_mid")
    justin_high_v = placement_row.get("justin_high")
    oop_caveat: str | None = None
    oop_signal: str = "none"  # none | neutral | adverse | severe
    if oop_n >= 1 and oop_min_v is not None and justin_mid_v is not None:
        if justin_high_v is not None and justin_high_v < oop_min_v:
            # Even the high projection is below the OOP floor — strongest signal
            severity = "severe" if oop_n >= 10 else "adverse_small_sample"
            oop_signal = severity
            sample_phrase = "" if oop_n >= 10 else f" (small sample n={oop_n} — directional only)"
            oop_caveat = (
                f"Justin's HIGH projection {justin_high_v}% is below the observed OOP floor "
                f"{oop_min_v}%{sample_phrase}"
            )
        elif justin_mid_v < oop_min_v:
            oop_signal = "adverse" if oop_n >= 10 else "adverse_small_sample"
            sample_phrase = "" if oop_n >= 10 else f" (small sample n={oop_n} — directional only)"
            oop_caveat = (
                f"Justin's midpoint {justin_mid_v}% is below the observed OOP floor "
                f"{oop_min_v}%{sample_phrase}"
            )
        # else: Justin is above the OOP floor → no caveat, no noise

    # EC strength text from profile
    ec_strengths = profile.get("extracurriculars", {}).get("ec_strengths_by_target", {})
    ec_strength_text = ec_strengths.get(program_key)

    out = {
        "program_key": program_key,
        "program": placement_row["program"],
        "university": placement_row["university"],
        "tier": placement_row["tier"],

        # Verdicts
        "verdict": placement_row["final_verdict"],
        "verdict_label": placement_row["final_verdict_label"],
        "verdict_gpa_only": placement_row["gpa_only_verdict"],
        "ec_weight": placement_row["ec_weight"],
        "confidence": placement_row["confidence"],

        # Stats
        "n_accepted": placement_row["n_accepted"],
        "median_accepted_avg": placement_row["median_accepted_avg"],
        "min_avg": quartiles["min"],
        "p25": quartiles["p25"],
        "p50": quartiles["p50"],
        "p75": quartiles["p75"],
        "max_avg": quartiles["max"],

        # Justin's projection vs this program
        "justin_low": placement_row["justin_low"],
        "justin_mid": placement_row["justin_mid"],
        "justin_high": placement_row["justin_high"],
        "justin_percentile_low": placement_row["gpa_percentile_low"],
        "justin_percentile_mid": placement_row["gpa_percentile_mid"],
        "justin_percentile_high": placement_row["gpa_percentile_high"],

        # OOP signals
        "oop_n": oop_n,
        "oop_min": placement_row["oop_min"],
        "oop_mean": placement_row["oop_mean"],
        "oop_caveat": oop_caveat,
        "oop_signal": oop_signal,

        # Application requirements (Justin-cycle dates already shifted)
        "supp_app_required": requirements.get("supp_app_required"),
        "supp_app_type": requirements.get("supp_app_type"),
        "supp_app_url": requirements.get("supp_app_url"),
        "casper_required": requirements.get("casper_required"),
        "interview_required": requirements.get("interview_required"),
        "references_required": requirements.get("references_required"),
        "deadline_ouac": requirements.get("deadline_ouac"),
        "deadline_supp": requirements.get("deadline_supp"),
        "deadline_doc": requirements.get("deadline_doc"),
        "decision_window": requirements.get("decision_window"),
        "fee_cad": requirements.get("fee_cad"),
        "official_url": requirements.get("source_url"),
        "min_average_competitive": requirements.get("min_average_competitive"),
        "prereq_courses": requirements.get("prereq_courses", []),
        "prereq_notes": requirements.get("prereq_notes"),
        "requirements_confidence": requirements.get("confidence"),

        # Long-form text
        "reasoning": placement_row["reasoning"],
        "ec_strength_text": ec_strength_text,

        # Distribution histogram bins (for the chart)
        "histogram_bins": histogram,
    }
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Action items
# ──────────────────────────────────────────────────────────────────────────────

def build_action_items(profile: dict, programs_tier1: list[dict],
                       programs_tier2: list[dict]) -> list[dict]:
    """Compose a date-sorted list of upcoming action items.

    Pulls from:
      - profile.extracurriculars.summer_2026_plans (Harvard MEDScience, HYRS)
      - per-program supp / OUAC deadlines (already shifted to Justin-cycle)
    """
    items: list[dict] = []
    today = date.today()

    # Summer 2026 plans
    summer = profile.get("extracurriculars", {}).get("summer_2026_plans", {})
    for entry in summer.get("confirmed", []):
        prog_name = entry.get("program", "")
        if entry.get("confirmation_deadline"):
            items.append({
                "date": entry["confirmation_deadline"],
                "label": f"Confirm enrollment: {prog_name}",
                "category": "summer_program",
                "priority": "high",
            })
        if entry.get("payment_deadline"):
            cost = entry.get("cost_usd")
            cost_str = f" (${cost:,} USD)" if cost else ""
            items.append({
                "date": entry["payment_deadline"],
                "label": f"Submit payment: {prog_name}{cost_str}",
                "category": "summer_program",
                "priority": "high",
            })
        if entry.get("welcome_letter_expected"):
            items.append({
                "date": entry["welcome_letter_expected"],
                "label": f"Welcome letter expected: {prog_name}",
                "category": "summer_program",
                "priority": "info",
            })
    for entry in summer.get("pending_decisions", []):
        items.append({
            "date": None,
            "date_label": entry.get("decision_expected", "TBD"),
            "label": f"Decision pending: {entry.get('program', '')}",
            "category": "summer_program",
            "priority": "info",
        })

    # Per-program deadlines (Tier 1 + Tier 2). De-dupe identical (date, program-set) pairs.
    seen: set[tuple] = set()
    for prog in programs_tier1 + programs_tier2:
        program_label = f"{prog['university']} — {prog['program']}"
        for field, label_template in [
            ("deadline_ouac", "OUAC equal-consideration: {p}"),
            ("deadline_supp", "Supplementary application due: {p}"),
            ("deadline_doc", "Documents due: {p}"),
        ]:
            d = prog.get(field)
            if not d:
                continue
            key = (d, field, program_label)
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "date": d,
                "label": label_template.format(p=program_label),
                "category": "application_deadline",
                "priority": "high" if prog.get("tier") == 1 else "medium",
            })

    # Sort by date (None goes last)
    items.sort(key=lambda x: (x.get("date") is None, x.get("date") or ""))

    # Annotate "days from today" for items with concrete dates
    for item in items:
        d_str = item.get("date")
        if d_str:
            try:
                d_dt = datetime.strptime(d_str, "%Y-%m-%d").date()
                item["days_from_today"] = (d_dt - today).days
            except ValueError:
                item["days_from_today"] = None

    return items


# ──────────────────────────────────────────────────────────────────────────────
# Build orchestration
# ──────────────────────────────────────────────────────────────────────────────

CAVEATS = [
    {
        "label": "Self-selection bias",
        "body": "Reddit users overwhelmingly post when they're accepted (~93-99% of decisions reported are acceptances). Treat all 'accepted average' numbers as the FLOOR of what gets in, not as a 50/50 cutoff line. Justin's percentile is relative to admitted students, not raw applicant pools.",
    },
    {
        "label": "OOP small samples",
        "body": "Out-of-province sample sizes are 4-12 reports per program. The verdict model treats OOP floors as directional only when n_oop < 10 — small-sample minimums are too noisy to override percentile-based verdicts.",
    },
    {
        "label": "McMaster BHSc OOP yellow flag",
        "body": "Only 5 OOP-accepted reports for McMaster BHSc across 4 cycles, all with averages ≥ 97.8%. The verdict model surfaces this as directional rather than verdict-changing, but it suggests the OOP bar may be meaningfully higher than in-province. Justin should know this.",
    },
    {
        "label": "Schema drift across cycles",
        "body": "The 4 Reddit forms used different question sets across years. The normalizer maps everything to a canonical 'best_avg' field. See workflows/clean_application_data.md for details.",
    },
    {
        "label": "2025-26 cycle still in progress",
        "body": "The 2025-2026 cycles (Ontario + Alberta) are still receiving submissions through ~end of May 2026. Numbers from that cycle are provisional and skew toward earlier-cycle decisions.",
    },
    {
        "label": "Tier-2 requirements confidence: medium",
        "body": "All 9 Tier-2 requirement entries are confidence=medium. Prerequisite courses are high-confidence (well-known and stable); specific dates default to the universal Jan 15 OUAC date and competitive averages are educated guesses anchored to Reddit data.",
    },
    {
        "label": "Tier-3/4 not curated",
        "body": "Tier-3 (Waterloo CS variants) and Tier-4 (UAlberta) program requirements have NOT been curated. Their checklist rows are blank.",
    },
    {
        "label": "Dates are shifted +1 year from cycle template",
        "body": "Curated requirements use the 2025-2026 cycle as a template. The dashboard shifts every date by +365 days to reflect Justin's actual application cycle (2026-2027). OUAC and supp deadlines may shift by ±1 day in the actual cycle — verify against official sources before relying on exact dates.",
    },
]


def build_data() -> dict:
    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found. Run tools/build_sqlite.py first.")
    if not PROFILE_PATH.exists():
        sys.exit(f"ERROR: {PROFILE_PATH} not found.")

    profile = load_profile()
    conn = sqlite3.connect(DB_PATH)
    try:
        placement_rows = query_placement(conn)
        all_programs: list[dict] = []
        for row in placement_rows:
            all_programs.append(build_program_object(row, conn, profile))

        tier1 = [p for p in all_programs if p["tier"] == 1]
        tier2 = [p for p in all_programs if p["tier"] == 2]
        tier3 = [p for p in all_programs if p["tier"] == 3]
        tier4 = [p for p in all_programs if p["tier"] == 4]

        yoy = query_yoy_trends(conn)
        timeline = query_decision_timeline(conn)
        cycles = query_cycles(conn)
    finally:
        conn.close()

    action_items = build_action_items(profile, tier1, tier2)

    # Strip provenance noise from the profile copy that goes to the page
    profile_for_page = {k: v for k, v in profile.items() if not k.startswith("_")}

    data = {
        "build_timestamp": datetime.now().isoformat(timespec="seconds"),
        "cycle_label": JUSTIN_CYCLE_LABEL,
        "profile": profile_for_page,
        "tier1": tier1,
        "tier2": tier2,
        "tier3": tier3,
        "tier4": tier4,
        "yoy_trends": yoy,
        "decision_timeline": timeline,
        "action_items": action_items,
        "data_quality": {
            "cycles": cycles,
            "caveats": CAVEATS,
        },
    }
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-summary", action="store_true",
                        help="Print summary stats of the existing docs/data.json instead of rebuilding")
    args = parser.parse_args()

    if args.print_summary:
        if not OUT_PATH.exists():
            sys.exit(f"ERROR: {OUT_PATH} not found.")
        data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        print(f"build_timestamp: {data['build_timestamp']}")
        print(f"cycle_label:     {data['cycle_label']}")
        print(f"tier1 programs:  {len(data['tier1'])}")
        print(f"tier2 programs:  {len(data['tier2'])}")
        print(f"tier3 programs:  {len(data['tier3'])}")
        print(f"tier4 programs:  {len(data['tier4'])}")
        print(f"yoy_trends:      {len(data['yoy_trends'])}")
        print(f"action_items:    {len(data['action_items'])}")
        print(f"caveats:         {len(data['data_quality']['caveats'])}")
        return 0

    data = build_data()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Wrote {OUT_PATH.relative_to(PROJECT_ROOT)}  ({size_kb:.1f} KB)")
    print()
    print(f"  build_timestamp: {data['build_timestamp']}")
    print(f"  cycle_label:     {data['cycle_label']}")
    print(f"  tier1 programs:  {len(data['tier1'])}")
    print(f"  tier2 programs:  {len(data['tier2'])}")
    print(f"  tier3 programs:  {len(data['tier3'])}")
    print(f"  tier4 programs:  {len(data['tier4'])}")
    print(f"  yoy_trends:      {len(data['yoy_trends'])} program(s)")
    print(f"  action_items:    {len(data['action_items'])}")
    print(f"  caveats:         {len(data['data_quality']['caveats'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
