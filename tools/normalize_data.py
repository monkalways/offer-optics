"""Normalize the 4 raw cycle CSVs into a single canonical pandas DataFrame.

Reads .tmp/raw/{cycle}_responses.csv files written by fetch_sheet.py and emits
.tmp/processed/applications.parquet plus a .tmp/processed/normalize_qa.md report
listing coverage stats and the top unmapped university/program strings (for
iterative pattern expansion).

Usage:
    python tools/normalize_data.py
    python tools/normalize_data.py --cycle 2023-2024   # debug a single cycle
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / ".tmp" / "raw"
PROCESSED_DIR = PROJECT_ROOT / ".tmp" / "processed"
PROGRAMS_YAML = PROJECT_ROOT / "config" / "programs.yaml"

# ──────────────────────────────────────────────────────────────────────────────
# Per-cycle header → canonical field mapping
# Headers must match exactly (after .strip()). When a header is missing or
# blank in the source, we fall back to the column INDEX given in `*_INDEX_FALLBACK`.
# ──────────────────────────────────────────────────────────────────────────────

# Canonical field names used everywhere downstream:
#   timestamp           — submission timestamp (str, raw)
#   university_raw      — free-text university string
#   program_raw         — free-text program string
#   ouac_code           — OUAC/OCAS program code (often unreliable)
#   decision_raw        — free-text decision string
#   acceptance_avg_raw  — single "best available average" string for the application
#   g11_final_raw, g12_midterm_raw, g12_predicted_raw, g12_final_raw — 23-24 only
#   applied_date_raw    — application submission date string
#   decision_date_raw   — decision-received date string
#   citizenship_raw     — country of citizenship (free-text)
#   province_raw        — province / state / territory of residence (free-text)
#   country_raw         — country of residence (23-24 only)
#   applicant_type_raw  — '101'/'105' (22-23) or 'Group A'/'Group B' (24-25/25-26)
#   supp_app_raw        — supp-app type free text (24-25/25-26 only) e.g. 'KIRA', 'AIF, KIRA'
#   supp_app_notes      — long-form supp-app description (24-25/25-26 only)
#   extracurriculars    — long-form ECs (22-23/23-24 only)
#   test_scores_raw     — AP/IB/SAT/ACT etc. (23-24 only)
#   scholarship_raw     — scholarship/aid mentions (23-24 only)
#   reddit_username, discord_username — usernames where reported
#   comments            — additional comments

HEADER_MAP: dict[str, dict[str, str]] = {
    "2022-2023": {
        "Timestamp": "timestamp",
        "What program did you apply to?": "program_raw",
        "Which university was this program from?": "university_raw",
        "What was your average when accepted? (average for particular program)": "acceptance_avg_raw",
        "What date was the offer/rejection/deferral received?": "decision_date_raw",
        "Did you add any notable extra curricular activities or special circumstances to your application?": "extracurriculars",
        "Are you a 101 or 105 applicant?": "applicant_type_raw",
        "Accepted, rejected, waitlisted, or deferred? (if deffered let us know to which program)": "decision_raw",
        "Exact discord or reddit username": "discord_username",
        "Any additional comments?(discord username would be preferred)": "comments",
    },
    "2023-2024": {
        "Timestamp": "timestamp",
        "OUAC/OCAS Program Code": "ouac_code",
        "What program did you apply to?": "program_raw",
        "What university did you apply to?": "university_raw",
        "Were you accepted, rejected, waitlisted or deferred?": "decision_raw",
        "Grade 11 Final Average": "g11_final_raw",
        "Grade 12 Midterm Average": "g12_midterm_raw",
        "Grade 12 Predicted Final Average": "g12_predicted_raw",
        "Grade 12 Final Average": "g12_final_raw",
        "Acceptance Average": "acceptance_avg_raw",
        "Any other exam and/or test scores you submitted:": "test_scores_raw",
        "Mention any notable extra curricular activities or special circumstances to your application?": "extracurriculars",
        "What date did you apply?": "applied_date_raw",
        "What date did you receive the offer/rejection/deferral?": "decision_date_raw",
        "Did you receive any scholarship or financial aid offer?": "scholarship_raw",
        "Country of Citizenship": "citizenship_raw",
        "Country of Residence": "country_raw",
        "Province/State/Territory of Residence": "province_raw",
        "Reddit username": "reddit_username",
        "Discord username": "discord_username",
        "Any additional comments? (If deferred, mention to which program here)": "comments",
    },
    "2024-2025": {
        "Timestamp": "timestamp",
        "University": "university_raw",
        "OUAC Code": "ouac_code",
        "Program name": "program_raw",
        "Decision": "decision_raw",
        "Top 6 Average": "acceptance_avg_raw",
        "Group A or B?": "applicant_type_raw",
        "Application date": "applied_date_raw",
        "Date of decision": "decision_date_raw",
        "Citizenship": "citizenship_raw",
        "Province": "province_raw",
        "Supp App?": "supp_app_raw",
        "Notable info from supp app": "supp_app_notes",
        "Comments": "comments",
    },
    "2025-2026": {
        # NOTE: 2025-2026 col 0 has an empty header but contains the timestamp.
        # We rely on INDEX_FALLBACK below to map col 0 → timestamp.
        "University": "university_raw",
        "OUAC Code": "ouac_code",
        "Program name": "program_raw",
        "Decision": "decision_raw",
        "Top 6 Average": "acceptance_avg_raw",
        "Application date": "applied_date_raw",
        "Date of decision": "decision_date_raw",
        "Group A or B?": "applicant_type_raw",
        "Citizenship": "citizenship_raw",
        "Province": "province_raw",
        "Supp App?": "supp_app_raw",
        "Notable info from supp app": "supp_app_notes",
        "Comments": "comments",
    },
    # Alberta-specific 2025-2026 sheet (added 2026-04-07).
    # Headers in the source contain trailing whitespace and a literal newline
    # (e.g. 'University\n', 'Top 5/6 Average Grade '); .strip() in the loop
    # normalizes these so the keys below stay clean.
    "2025-2026-ab": {
        "Timestamp": "timestamp",
        "University": "university_raw",
        "Program/Degree name": "program_raw",
        "Top 5/6 Average Grade": "acceptance_avg_raw",
        "Date of Application": "applied_date_raw",
        "Date of Decision": "decision_date_raw",
        "Province": "province_raw",
        "Program Decision": "decision_raw",
        "Your Decision": "student_response_raw",  # what the student did with the offer
        "Supplemental Application": "supp_app_raw",
        "Extracurriculars, AP/IB, Online School?": "extracurriculars",
        "Comments?": "comments",
    },
}

INDEX_FALLBACK: dict[str, dict[int, str]] = {
    # 2025-26 col 0 has no header but is the submission timestamp
    "2025-2026": {0: "timestamp"},
}


# ──────────────────────────────────────────────────────────────────────────────
# Cleaners
# ──────────────────────────────────────────────────────────────────────────────

DECISION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(accept|accepeted|admitted|offer|conditional offer|in)\b", re.I), "accepted"),
    (re.compile(r"accept", re.I), "accepted"),
    (re.compile(r"reject|denied|out\b", re.I), "rejected"),
    (re.compile(r"defer", re.I), "deferred"),
    (re.compile(r"waitlist|wait\s*list", re.I), "waitlisted"),
    (re.compile(r"withdraw", re.I), "withdrawn"),
]


def norm_decision(s: Any) -> str | None:
    if s is None or pd.isna(s):
        return None
    text = str(s).strip()
    if not text:
        return None
    for pat, label in DECISION_PATTERNS:
        if pat.search(text):
            return label
    return None


def norm_average(s: Any) -> float | None:
    """Parse a percentage / numeric average. Returns None for unparseable / out-of-range."""
    if s is None or pd.isna(s):
        return None
    text = str(s).strip()
    if not text:
        return None
    text = text.rstrip("%").strip().replace(",", ".")
    # Handle cases like "95.5/100" or "95.5 (top 6)"
    m = re.match(r"^(-?\d+\.?\d*)", text)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    # GPA scale — can't compare to percentages
    if 0 < v <= 4.5:
        return None
    if v < 50 or v > 100:
        return None
    return round(v, 2)


def norm_applicant_type(s: Any) -> str | None:
    """Normalize 101/105 and Group A/B to a single canonical 101/105."""
    if s is None or pd.isna(s):
        return None
    text = str(s).strip().lower()
    if not text:
        return None
    if "101" in text:
        return "101"
    if "105" in text:
        return "105"
    if "group a" in text or text == "a":
        return "101"
    if "group b" in text or text == "b":
        return "105"
    return None


# Per-cycle date order hint. Resolves ambiguous values like "5/7/2025":
#   "MDY" → May 7 (US-style, 24-25/25-26 ON sheets)
#   "DMY" → July 5 (UK-style, 23-24 ON sheet, 25-26 AB sheet)
DATE_ORDER: dict[str, str] = {
    "2022-2023": "MDY",
    "2023-2024": "DMY",  # observed: '15/12/2023', '6 Oct 2023'
    "2024-2025": "MDY",
    "2025-2026": "MDY",
    "2025-2026-ab": "DMY",  # observed: '27/10/2025', '01/10/2025'
}

_DATE_FORMATS_MDY = [
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
    "%d/%m/%Y %H:%M:%S",  # fall back to DMY if MDY fails
    "%d/%m/%Y",
]
_DATE_FORMATS_DMY = [
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y",
    "%m/%d/%Y %H:%M:%S",  # fall back to MDY if DMY fails
    "%m/%d/%Y",
]
_DATE_FORMATS_TEXTUAL = [
    "%Y-%m-%d",
    "%d %b %Y",
    "%d %B %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
]


def norm_date(s: Any, order: str = "MDY") -> str | None:
    if s is None or pd.isna(s):
        return None
    text = str(s).strip()
    if not text:
        return None
    formats = (_DATE_FORMATS_DMY if order == "DMY" else _DATE_FORMATS_MDY) + _DATE_FORMATS_TEXTUAL
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None  # leave as None; raw stays available in *_raw


def norm_str(s: Any) -> str | None:
    if s is None or pd.isna(s):
        return None
    text = str(s).strip()
    return text or None


# ──────────────────────────────────────────────────────────────────────────────
# University + program matching
# ──────────────────────────────────────────────────────────────────────────────

# University-level patterns. Used as a fallback when no full program pattern matches,
# so we can still attribute the row to a university even if the specific program
# isn't in our config.
UNIVERSITY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("mcmaster",       re.compile(r"mcmaster|\bmac\b", re.I)),
    ("queens",         re.compile(r"queen", re.I)),
    ("waterloo",       re.compile(r"waterloo|\buw\b|\buwaterloo\b", re.I)),
    ("uoft_stgeorge",  re.compile(r"(?:utsg|st\.?\s*george)", re.I)),
    ("uoft_utm",       re.compile(r"\butm\b|mississauga", re.I)),
    ("uoft_utsc",      re.compile(r"\butsc\b|scarborough", re.I)),
    ("uoft",           re.compile(r"uoft|u\s*of\s*t\b|toronto|utoronto", re.I)),
    ("western",        re.compile(r"western|\buwo\b", re.I)),
    ("guelph",         re.compile(r"guelph", re.I)),
    ("ottawa",         re.compile(r"ottawa|uottawa", re.I)),
    ("brock",          re.compile(r"brock", re.I)),
    ("ualberta",       re.compile(r"alberta|\buofa\b|\bu\s*of\s*a\b|\bua\b", re.I)),
    ("ubc",            re.compile(r"\bubc\b|british columbia", re.I)),
    ("mcgill",         re.compile(r"mcgill", re.I)),
    ("laurier",        re.compile(r"laurier", re.I)),
    ("york",           re.compile(r"\byork\b", re.I)),
    ("carleton",       re.compile(r"carleton", re.I)),
    ("ryerson",        re.compile(r"ryerson|\btmu\b|toronto\s*metropolitan", re.I)),
    ("ontario_tech",   re.compile(r"ontario\s*tech|\buoit\b", re.I)),
    ("trent",          re.compile(r"trent", re.I)),
    ("windsor",        re.compile(r"windsor", re.I)),
    ("laurentian",     re.compile(r"laurentian", re.I)),
    ("lakehead",       re.compile(r"lakehead", re.I)),
    ("nipissing",      re.compile(r"nipissing", re.I)),
    ("queens_kingston", re.compile(r"kingston", re.I)),  # rare alt for Queen's
    ("usask",          re.compile(r"saskatchewan|usask", re.I)),
    ("ucalgary",       re.compile(r"calgary|ucalgary", re.I)),
    ("dalhousie",      re.compile(r"dalhousie|\bdal\b", re.I)),
    ("memorial",       re.compile(r"memorial|mun\b", re.I)),
    ("acadia",         re.compile(r"acadia", re.I)),
    ("concordia",      re.compile(r"concordia", re.I)),
    ("uvic",           re.compile(r"\buvic\b|victoria", re.I)),
    ("ubco",           re.compile(r"\bubco\b|okanagan", re.I)),
    ("rmc",            re.compile(r"\brmc\b|royal\s*military", re.I)),
    ("sfu",            re.compile(r"\bsfu\b|simon\s*fraser", re.I)),
    ("ocad",           re.compile(r"\bocad\b", re.I)),
    ("mt_allison",     re.compile(r"mount\s*allison|\bmta\b", re.I)),
    ("unb",            re.compile(r"\bunb\b|new\s*brunswick", re.I)),
]


def load_programs() -> list[dict]:
    data = yaml.safe_load(PROGRAMS_YAML.read_text(encoding="utf-8"))
    progs = data.get("programs", [])
    # Pre-compile match patterns
    for p in progs:
        p["_compiled"] = [re.compile(pat) for pat in p.get("match_patterns", [])]
    return progs


def match_program(university_raw: Any, program_raw: Any, programs: list[dict]) -> tuple[str | None, str | None]:
    """Return (university_key, program_key). Both may be None.

    Strategy:
      1. Concatenate "{university} {program}" and try every program's match_patterns.
         First hit wins → returns (university_key from that program, program_key).
      2. If no program pattern matches, fall back to UNIVERSITY_PATTERNS on the same
         combined string → returns (university_key, None).
      3. If still nothing → (None, None).
    """
    combined_parts: list[str] = []
    for s in (university_raw, program_raw):
        if s is None or (isinstance(s, float) and pd.isna(s)):
            continue
        s_str = str(s).strip()
        if s_str:
            combined_parts.append(s_str)
    if not combined_parts:
        return None, None
    combined = " ".join(combined_parts)

    # Step 1: full program match
    for prog in programs:
        for compiled in prog["_compiled"]:
            if compiled.search(combined):
                return prog["university_key"], prog["key"]

    # Step 2: university-only fallback
    for uni_key, pat in UNIVERSITY_PATTERNS:
        if pat.search(combined):
            return uni_key, None

    return None, None


# ──────────────────────────────────────────────────────────────────────────────
# Per-cycle row processing
# ──────────────────────────────────────────────────────────────────────────────

JUNK_ROW_PATTERNS = [
    re.compile(r"editing of this spreadsheet is not permitted", re.I),
    re.compile(r"do not request access to be an editor", re.I),
    re.compile(r"^https?://", re.I),
]


def is_junk_row(row: list) -> bool:
    parts: list[str] = []
    for s in row:
        if s is None or (isinstance(s, float) and pd.isna(s)):
            continue
        s_str = str(s).strip()
        if s_str:
            parts.append(s_str)
    joined = " ".join(parts).strip()
    if not joined:
        return True
    for pat in JUNK_ROW_PATTERNS:
        if pat.search(joined):
            return True
    return False


def normalize_cycle(cycle: str, programs: list[dict], spreadsheet_cfg: dict) -> tuple[pd.DataFrame, dict]:
    csv_path = RAW_DIR / f"{cycle}_responses.csv"
    if not csv_path.exists():
        sys.exit(f"ERROR: {csv_path} not found. Run tools/fetch_sheet.py first.")

    raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_values=[""])
    headers = list(raw.columns)
    if cycle not in HEADER_MAP:
        sys.exit(f"ERROR: cycle '{cycle}' has no entry in HEADER_MAP. Add one in normalize_data.py.")
    header_map = HEADER_MAP[cycle]
    fallback = INDEX_FALLBACK.get(cycle, {})
    region = spreadsheet_cfg.get("region", "ON")
    date_order = DATE_ORDER.get(cycle, "MDY")

    # Build a column-index → canonical-field mapping
    col_to_field: dict[int, str] = {}
    for i, h in enumerate(headers):
        h_clean = (h or "").strip()
        if h_clean in header_map:
            col_to_field[i] = header_map[h_clean]
        elif i in fallback:
            col_to_field[i] = fallback[i]

    # Sanity-check that the critical fields are mapped
    mapped_fields = set(col_to_field.values())
    required = {"university_raw", "program_raw", "decision_raw"}
    missing = required - mapped_fields
    if missing:
        sys.exit(f"ERROR [{cycle}]: required canonical fields not mapped from headers: {missing}\n"
                 f"Headers were: {headers}")

    rows_out: list[dict] = []
    junked = 0
    for src_idx, row in enumerate(raw.itertuples(index=False, name=None)):
        if is_junk_row(list(row)):
            junked += 1
            continue
        rec: dict[str, Any] = {
            "cycle": cycle,
            "region": region,
            "source_row": src_idx + 2,  # +2 for header + 1-based
        }
        for i, val in enumerate(row):
            field = col_to_field.get(i)
            if field is None:
                continue
            rec[field] = val if (val is not None and val != "") else None
        rows_out.append(rec)

    if not rows_out:
        return pd.DataFrame(), {"cycle": cycle, "junked": junked, "kept": 0}

    df = pd.DataFrame(rows_out)

    # Ensure all canonical columns exist (so the schemas line up across cycles)
    for col in [
        "timestamp", "university_raw", "program_raw", "ouac_code", "decision_raw",
        "acceptance_avg_raw", "g11_final_raw", "g12_midterm_raw", "g12_predicted_raw", "g12_final_raw",
        "applied_date_raw", "decision_date_raw", "citizenship_raw", "country_raw", "province_raw",
        "applicant_type_raw", "supp_app_raw", "supp_app_notes", "student_response_raw",
        "extracurriculars", "test_scores_raw", "scholarship_raw",
        "reddit_username", "discord_username", "comments",
    ]:
        if col not in df.columns:
            df[col] = None

    # Apply normalizers (using per-cycle date order)
    df["decision"] = df["decision_raw"].map(norm_decision)
    df["acceptance_avg"] = df["acceptance_avg_raw"].map(norm_average)
    df["g11_final"] = df["g11_final_raw"].map(norm_average)
    df["g12_midterm"] = df["g12_midterm_raw"].map(norm_average)
    df["g12_predicted"] = df["g12_predicted_raw"].map(norm_average)
    df["g12_final"] = df["g12_final_raw"].map(norm_average)
    df["applicant_type"] = df["applicant_type_raw"].map(norm_applicant_type)
    df["applied_date"] = df["applied_date_raw"].map(lambda v: norm_date(v, date_order))
    df["decision_date"] = df["decision_date_raw"].map(lambda v: norm_date(v, date_order))
    df["timestamp_iso"] = df["timestamp"].map(lambda v: norm_date(v, date_order))
    df["province"] = df["province_raw"].map(norm_str)
    df["citizenship"] = df["citizenship_raw"].map(norm_str)

    # Single "best available average" — prefer cycle-specific best
    def best_avg(row):
        for col in ("acceptance_avg", "g12_final", "g12_predicted", "g12_midterm", "g11_final"):
            v = row.get(col)
            if v is not None and not pd.isna(v):
                return v
        return None
    df["best_avg"] = df.apply(best_avg, axis=1)

    # University + program matching
    uni_keys: list[str | None] = []
    prog_keys: list[str | None] = []
    for u, p in zip(df["university_raw"], df["program_raw"]):
        uk, pk = match_program(u, p, programs)
        uni_keys.append(uk)
        prog_keys.append(pk)
    df["university_key"] = uni_keys
    df["program_key"] = prog_keys

    stats = {
        "cycle": cycle,
        "junked": junked,
        "kept": len(df),
        "decision_mapped": int(df["decision"].notna().sum()),
        "best_avg_mapped": int(df["best_avg"].notna().sum()),
        "applicant_type_mapped": int(df["applicant_type"].notna().sum()),
        "university_mapped": int(df["university_key"].notna().sum()),
        "program_mapped": int(df["program_key"].notna().sum()),
    }
    return df, stats


# ──────────────────────────────────────────────────────────────────────────────
# QA report
# ──────────────────────────────────────────────────────────────────────────────

def write_qa_report(per_cycle_stats: list[dict], df: pd.DataFrame) -> None:
    out_path = PROCESSED_DIR / "normalize_qa.md"
    lines: list[str] = []
    lines.append("# Normalize QA Report")
    lines.append("")
    lines.append(f"_Generated {datetime.now().isoformat(timespec='seconds')}_")
    lines.append("")
    lines.append("## Per-cycle coverage")
    lines.append("")
    lines.append("| Cycle | Junked | Kept | Decision | Avg | AppType | University | Program |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for s in per_cycle_stats:
        kept = s["kept"]
        def pct(n: int) -> str:
            return f'{n} ({100*n/kept:.0f}%)' if kept else f'{n}'
        lines.append(
            f"| {s['cycle']} | {s['junked']} | {kept} | "
            f"{pct(s['decision_mapped'])} | {pct(s['best_avg_mapped'])} | "
            f"{pct(s['applicant_type_mapped'])} | {pct(s['university_mapped'])} | "
            f"{pct(s['program_mapped'])} |"
        )
    lines.append("")

    # Top unmapped university strings
    unmapped_uni = (
        df[df["university_key"].isna()]["university_raw"]
        .dropna().astype(str).str.strip().str.lower()
    )
    uni_counter = Counter(unmapped_uni)
    lines.append("## Top 30 unmapped UNIVERSITY strings")
    lines.append("")
    if uni_counter:
        lines.append("| Count | university_raw |")
        lines.append("|---:|---|")
        for s, c in uni_counter.most_common(30):
            lines.append(f"| {c} | `{s}` |")
    else:
        lines.append("_(none — every row mapped to a university)_")
    lines.append("")

    # Top unmapped program strings within each Tier-1 university
    lines.append("## Unmapped PROGRAM strings within target universities (top 20 per uni)")
    lines.append("")
    for uni_key in ("mcmaster", "queens", "waterloo", "uoft_stgeorge", "uoft_utm", "uoft_utsc",
                    "uoft", "western", "guelph", "ottawa", "ualberta"):
        sub = df[(df["university_key"] == uni_key) & (df["program_key"].isna())]
        if sub.empty:
            continue
        progs = (sub["program_raw"].dropna().astype(str).str.strip().str.lower())
        c = Counter(progs)
        lines.append(f"### {uni_key}  ({len(sub)} unmapped rows)")
        lines.append("")
        lines.append("| Count | program_raw |")
        lines.append("|---:|---|")
        for s, n in c.most_common(20):
            lines.append(f"| {n} | `{s}` |")
        lines.append("")

    # Decision distribution after normalization
    lines.append("## Decision distribution (post-normalization)")
    lines.append("")
    lines.append("| Cycle | accepted | rejected | deferred | waitlisted | withdrawn | unknown |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for cycle in df["cycle"].unique():
        sub = df[df["cycle"] == cycle]
        cnt = sub["decision"].fillna("unknown").value_counts().to_dict()
        lines.append(
            f"| {cycle} | {cnt.get('accepted',0)} | {cnt.get('rejected',0)} | "
            f"{cnt.get('deferred',0)} | {cnt.get('waitlisted',0)} | "
            f"{cnt.get('withdrawn',0)} | {cnt.get('unknown',0)} |"
        )
    lines.append("")

    # Quick rows-per-target-program count
    lines.append("## Rows per Tier-1 target program (post-normalization)")
    lines.append("")
    lines.append("| program_key | total | accepted | rejected | deferred | waitlisted |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for prog_key in ("mcmaster_bhsc", "queens_bhsc", "waterloo_cs", "uoft_lifesci_stgeorge"):
        sub = df[df["program_key"] == prog_key]
        cnt = sub["decision"].fillna("unknown").value_counts().to_dict()
        lines.append(
            f"| {prog_key} | {len(sub)} | {cnt.get('accepted',0)} | "
            f"{cnt.get('rejected',0)} | {cnt.get('deferred',0)} | {cnt.get('waitlisted',0)} |"
        )
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  QA report  -> {out_path.relative_to(PROJECT_ROOT)}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", default="all", help="Specific cycle (e.g. '2023-2024') or 'all'")
    args = parser.parse_args()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    programs = load_programs()
    print(f"Loaded {len(programs)} programs from config/programs.yaml")

    # Load spreadsheet configs from programs.yaml so cycles are data-driven
    full_yaml = yaml.safe_load(PROGRAMS_YAML.read_text(encoding="utf-8"))
    spreadsheet_configs = full_yaml.get("spreadsheets", [])
    cycles_to_run: list[dict]
    if args.cycle == "all":
        cycles_to_run = spreadsheet_configs
    else:
        cycles_to_run = [c for c in spreadsheet_configs if c["cycle"] == args.cycle]
        if not cycles_to_run:
            sys.exit(f"ERROR: cycle '{args.cycle}' not found in config/programs.yaml")

    print()
    frames = []
    stats_all = []
    for cfg in cycles_to_run:
        cycle = cfg["cycle"]
        df, stats = normalize_cycle(cycle, programs, cfg)
        kept = stats["kept"]
        print(f"  {cycle}: kept {kept} (junked {stats['junked']}); "
              f"decision {stats['decision_mapped']}, "
              f"avg {stats['best_avg_mapped']}, "
              f"uni {stats['university_mapped']}, "
              f"prog {stats['program_mapped']}")
        frames.append(df)
        stats_all.append(stats)

    full = pd.concat(frames, ignore_index=True)

    # Drop columns we don't need in the final parquet (the *_raw stay for traceability)
    out_path = PROCESSED_DIR / "applications.parquet"
    full.to_parquet(out_path, index=False)
    print(f"\n  Wrote {len(full)} rows -> {out_path.relative_to(PROJECT_ROOT)}")

    write_qa_report(stats_all, full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
