"""Build (or refresh) the Google Sheets dashboard for Justin's application cycle.

Reads .tmp/applications.sqlite + config/justin_profile.json + config/programs.yaml,
then writes a single spreadsheet "Justin — University Application Dashboard 2026"
to the authorized user's Drive with 7 tabs. The spreadsheet ID is persisted to
.tmp/dashboard_state.json so subsequent runs refresh in place.

Usage:
    python tools/build_dashboard.py             # refresh existing or create new
    python tools/build_dashboard.py --create    # force a new spreadsheet
    python tools/build_dashboard.py --print-url # just print the existing URL
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml
from googleapiclient.errors import HttpError

# Import the auth helper from the sibling module
from google_auth import get_drive_service, get_sheets_service  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / ".tmp" / "applications.sqlite"
PROFILE_PATH = PROJECT_ROOT / "config" / "justin_profile.json"
PROGRAMS_YAML = PROJECT_ROOT / "config" / "programs.yaml"
STATE_PATH = PROJECT_ROOT / ".tmp" / "dashboard_state.json"

DASHBOARD_TITLE = "Justin — University Application Dashboard 2026"


# ──────────────────────────────────────────────────────────────────────────────
# State persistence (which spreadsheet ID we created previously)
# ──────────────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_or_create_spreadsheet(sheets_service, force_create: bool = False) -> tuple[str, bool]:
    """Return (spreadsheet_id, was_created). Reuses existing ID if possible."""
    state = load_state()
    sheet_id = state.get("sheet_id")
    if sheet_id and not force_create:
        try:
            sheets_service.spreadsheets().get(
                spreadsheetId=sheet_id, fields="properties.title"
            ).execute()
            return sheet_id, False
        except HttpError as e:
            if e.resp.status == 404:
                print(f"  Cached sheet ID {sheet_id} no longer exists; creating a new one.")
            else:
                raise

    body = {"properties": {"title": DASHBOARD_TITLE}}
    resp = sheets_service.spreadsheets().create(body=body, fields="spreadsheetId").execute()
    new_id = resp["spreadsheetId"]
    state.update({
        "sheet_id": new_id,
        "title": DASHBOARD_TITLE,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_state(state)
    return new_id, True


# ──────────────────────────────────────────────────────────────────────────────
# Data helpers
# ──────────────────────────────────────────────────────────────────────────────

def query_db(sql: str, params: dict | None = None) -> tuple[list[str], list[tuple]]:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(sql, params or {})
        rows = cur.fetchall()
        headers = [d[0] for d in cur.description] if cur.description else []
        return headers, rows
    finally:
        conn.close()


def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def load_program_tiers() -> dict[str, int]:
    data = yaml.safe_load(PROGRAMS_YAML.read_text(encoding="utf-8"))
    return {p["key"]: p.get("tier") for p in data.get("programs", [])}


def stringify_cell(v: Any) -> Any:
    """Convert non-JSON-serializable values to types Sheets API accepts."""
    if v is None:
        return ""
    if isinstance(v, float) and v != v:  # NaN
        return ""
    return v


def normalize_rows(rows: list[list]) -> list[list]:
    return [[stringify_cell(c) for c in row] for row in rows]


# ──────────────────────────────────────────────────────────────────────────────
# Tab builders — each returns a Tab dict with 'cells' and optional formatting hints
# ──────────────────────────────────────────────────────────────────────────────

def build_overview() -> dict:
    profile = load_profile()
    refreshed = datetime.now().strftime("%Y-%m-%d %H:%M")

    cells: list[list] = []
    cells.append(["Justin's University Application Dashboard 2026"])
    cells.append([f"Last refreshed: {refreshed}"])
    cells.append([""])

    # Profile section
    cells.append(["PROFILE"])
    cells.append(["Name", profile["name"]])
    cells.append(["High school", profile["high_school"]])
    cells.append(["City / Province", f"{profile['city']}, {profile['province']}"])
    cells.append(["Applicant type", f"OUAC {profile['applicant_type']} (out-of-province for Ontario schools)"])
    cells.append([""])

    # Projected G12 averages
    avg = profile["grade_12_projected_top6_average"]
    cells.append(["PROJECTED GRADE 12 TOP-6 AVERAGE"])
    cells.append(["Low", "Midpoint", "High"])
    cells.append([avg["low"], avg["midpoint"], avg["high"]])
    cells.append([""])
    cells.append(["Projected courses (midpoint)"])
    cells.append(["Course", "Low", "High", "Midpoint"])
    for c in profile["grade_12_projected_courses"]:
        cells.append([c["course"], c["low"], c["high"], c["midpoint"]])
    cells.append([""])

    # Tier-1 placement summary — reads from placement table (populated by
    # tools/analyze_program.py). Falls back to "not analyzed" if empty.
    cells.append(["TIER 1 — TOP TARGETS (verdict reflects GPA percentile + EC leverage)"])
    cells.append([
        "Program", "n_accepted", "median_accepted",
        "Justin percentile", "GPA-only verdict", "EC-adjusted verdict", "Confidence"
    ])
    headers, rows = query_db("""
        SELECT program, n_accepted, median_accepted_avg,
               gpa_percentile_mid, gpa_only_verdict, final_verdict_label,
               confidence
        FROM placement
        WHERE tier = 1
        ORDER BY
            CASE final_verdict
                WHEN 'safety' THEN 1
                WHEN 'target' THEN 2
                WHEN 'reach' THEN 3
                WHEN 'hard_reach' THEN 4
                ELSE 5
            END,
            n_accepted DESC
    """)
    if not rows:
        cells.append(["(placement table empty — run tools/analyze_program.py)"])
    else:
        for row in rows:
            program, n_acc, median_acc, pct, gpa_verdict, final_label, conf = row
            pct_str = f"{pct:.0f}th" if pct is not None else "—"
            cells.append([program, n_acc, median_acc, pct_str, gpa_verdict, final_label, conf])

    cells.append([""])
    cells.append(["KEY FINDINGS — read this first"])
    cells.append(["1.", "McMaster BHSc OOP minimum observed avg = 97.8% across 4 cycles (n=5). Justin at 95.5% is below this floor. The OOP supplementary application bar at McMaster BHSc is meaningfully higher than in-province."])
    cells.append(["2.", "Waterloo CS cutoffs jumped sharply between 23-24 and 24-25: mean accepted avg moved from 94.1 to 97.7 and is holding there in 25-26."])
    cells.append(["3.", "McMaster BHSc accepted vs rejected averages differ by only 0.8 points in 24-25 — confirms the supplementary application + interview-style questions are the dominant signal, not raw GPA."])
    cells.append(["4.", "None of the Tier-1 programs use CASPer, interviews, or reference letters. Each requires a different supplementary application (Mac written essay, Queen's PSE, Waterloo AIF). UofT Life Sci has no supp app at all."])
    cells.append(["5.", "Reddit dataset is severely self-selected toward acceptances (~93-99% per cycle). All 'accepted average' numbers are floors, not 50/50 cutoffs."])
    cells.append([""])
    cells.append(["See 06_Data Quality for caveats and 02_Application Checklist for the deadline list."])

    return {"cells": normalize_rows(cells), "frozen_rows": 0, "header_rows": []}


def build_placement() -> dict:
    """Per-program placement summary + full reasoning text. Reads from the
    placement table populated by tools/analyze_program.py."""
    profile = load_profile()
    avg = profile["grade_12_projected_top6_average"]

    cells: list[list] = []
    cells.append([f"Placement summary — Justin's projected top-6 midpoint: {avg['midpoint']}% (low {avg['low']}, high {avg['high']})"])
    cells.append([
        "How to read: 'GPA-only verdict' is based purely on where Justin's midpoint sits in the accepted-average distribution. "
        "'EC-adjusted verdict' applies the supp-app / AIF leverage for programs where ECs materially affect admission. "
        "Only BHSc programs (McMaster, Queen's) give ECs enough weight to upgrade by a full tier; Waterloo CS-family AIFs can only rescue a hard_reach to a reach."
    ])
    cells.append([""])

    # Summary table
    cells.append([
        "Tier", "Program", "University", "n_accepted", "Median", "Justin pct",
        "GPA-only", "Final verdict", "Confidence", "EC weight"
    ])
    _, rows = query_db("""
        SELECT tier, program, university, n_accepted, median_accepted_avg,
               gpa_percentile_mid, gpa_only_verdict, final_verdict_label,
               confidence, ec_weight
        FROM placement
        ORDER BY tier,
            CASE final_verdict
                WHEN 'safety' THEN 1
                WHEN 'target' THEN 2
                WHEN 'reach' THEN 3
                WHEN 'hard_reach' THEN 4
                ELSE 5
            END,
            n_accepted DESC
    """)
    for row in rows:
        tier, program, university, n_acc, median_acc, pct, gpa_v, final_label, conf, ec_w = row
        pct_str = f"{pct:.0f}th" if pct is not None else "—"
        cells.append([tier, program, university, n_acc, median_acc, pct_str, gpa_v, final_label, conf, ec_w])

    cells.append([""])
    cells.append([""])
    cells.append(["DETAILED REASONING (read this for each program)"])
    cells.append([""])

    # Reasoning per program, grouped by tier
    _, reasoning_rows = query_db("""
        SELECT tier, program_key, university, program, final_verdict_label, reasoning
        FROM placement
        WHERE confidence != 'insufficient'
        ORDER BY tier, program_key
    """)
    current_tier = None
    for row in reasoning_rows:
        tier, program_key, university, program, final_label, reasoning = row
        if tier != current_tier:
            cells.append([""])
            cells.append([f"— Tier {tier} —"])
            current_tier = tier
        cells.append([f"[{final_label}] {university} — {program}"])
        cells.append([reasoning])
        cells.append([""])

    # Insufficient-data programs (listed briefly, no reasoning)
    _, insuf_rows = query_db("""
        SELECT tier, program_key, university, program, n_accepted
        FROM placement
        WHERE confidence = 'insufficient'
        ORDER BY tier, program_key
    """)
    if insuf_rows:
        cells.append([""])
        cells.append(["— Insufficient data (sample < 10) —"])
        for row in insuf_rows:
            tier, program_key, university, program, n = row
            cells.append([f"Tier {tier}: {university} — {program} (n={n})"])

    return {"cells": normalize_rows(cells), "frozen_rows": 4, "header_rows": [3]}


def build_per_program_detail() -> dict:
    headers, rows = query_db("""
        WITH ranked AS (
            SELECT a.program_key, a.best_avg,
                   ROW_NUMBER() OVER (PARTITION BY a.program_key ORDER BY a.best_avg) AS rn,
                   COUNT(*) OVER (PARTITION BY a.program_key) AS cnt
            FROM applications a
            WHERE a.decision = 'accepted' AND a.best_avg IS NOT NULL AND a.program_key IS NOT NULL
        ),
        quartiles AS (
            SELECT
                program_key,
                MAX(CASE WHEN rn = MAX(1, (cnt + 2) /  4) THEN best_avg END) AS p25,
                MAX(CASE WHEN rn = MAX(1, (cnt + 1) /  2) THEN best_avg END) AS p50,
                MAX(CASE WHEN rn = MAX(1, (3 * cnt + 3) / 4) THEN best_avg END) AS p75
            FROM ranked
            GROUP BY program_key
        ),
        agg AS (
            SELECT
                program_key,
                COUNT(*)        AS n_accepted,
                MIN(best_avg)   AS min_avg,
                AVG(best_avg)   AS mean_avg,
                MAX(best_avg)   AS max_avg
            FROM applications
            WHERE decision = 'accepted' AND best_avg IS NOT NULL AND program_key IS NOT NULL
            GROUP BY program_key
        ),
        oop AS (
            SELECT
                program_key,
                MIN(best_avg) AS oop_min,
                ROUND(AVG(best_avg), 1) AS oop_mean,
                COUNT(*) AS oop_n
            FROM applications
            WHERE decision = 'accepted'
              AND best_avg IS NOT NULL
              AND program_key IS NOT NULL
              AND province IS NOT NULL
              AND LOWER(province) NOT LIKE '%ontario%'
            GROUP BY program_key
        )
        SELECT
            p.tier                                     AS tier,
            a.program_key                              AS program_key,
            p.university                               AS university,
            p.program                                  AS program,
            a.n_accepted                               AS n,
            ROUND(a.min_avg, 1)                        AS min_avg,
            ROUND(q.p25, 1)                            AS p25,
            ROUND(q.p50, 1)                            AS median,
            ROUND(a.mean_avg, 1)                       AS mean,
            ROUND(q.p75, 1)                            AS p75,
            ROUND(a.max_avg, 1)                        AS max_avg,
            o.oop_n                                    AS oop_n,
            o.oop_mean                                 AS oop_mean,
            ROUND(o.oop_min, 1)                        AS oop_min,
            r.min_average_competitive                  AS official_min,
            CASE WHEN r.supp_app_required = 1 THEN 'yes' ELSE 'no' END AS supp_app,
            r.confidence                               AS req_confidence
        FROM agg a
        JOIN programs p ON p.program_key = a.program_key
        LEFT JOIN quartiles q ON q.program_key = a.program_key
        LEFT JOIN oop       o ON o.program_key = a.program_key
        LEFT JOIN requirements r ON r.program_key = a.program_key
        ORDER BY p.tier, a.n_accepted DESC
    """)

    cells: list[list] = [headers]
    cells.extend(list(r) for r in rows)
    return {"cells": normalize_rows(cells), "frozen_rows": 1, "header_rows": [0]}


def build_application_checklist() -> dict:
    headers, rows = query_db("""
        SELECT
            r.tier                                            AS tier,
            r.program_key                                     AS program_key,
            p.university                                      AS university,
            p.program                                         AS program,
            r.application_deadline_ouac                       AS ouac_deadline,
            r.application_deadline_supp                       AS supp_deadline,
            r.document_deadline                               AS doc_deadline,
            r.decision_release_window                         AS decision_window,
            CASE WHEN r.supp_app_required = 1 THEN 'YES' ELSE '—' END  AS supp_app,
            r.supp_app_type                                   AS supp_format,
            CASE WHEN r.casper_required = 1 THEN 'YES' ELSE '—' END    AS casper,
            CASE WHEN r.interview_required = 1 THEN 'YES' ELSE '—' END AS interview,
            CASE WHEN r.references_required = 1 THEN 'YES' ELSE '—' END AS refs,
            r.min_average_competitive                         AS official_min_avg,
            r.application_fee_cad                             AS fee_cad,
            r.confidence                                      AS confidence,
            r.source_url                                      AS source_url
        FROM requirements r
        JOIN programs p ON p.program_key = r.program_key
        ORDER BY r.application_deadline_ouac, r.application_deadline_supp NULLS LAST, r.tier, r.program_key
    """)

    cells: list[list] = [headers]
    cells.extend(list(r) for r in rows)
    return {"cells": normalize_rows(cells), "frozen_rows": 1, "header_rows": [0]}


def build_yoy_trends() -> dict:
    headers, rows = query_db("""
        SELECT
            p.program_key,
            p.program,
            a.cycle,
            COUNT(*)                            AS n_accepted,
            ROUND(AVG(a.best_avg), 1)           AS mean_avg,
            ROUND(MIN(a.best_avg), 1)           AS min_avg,
            ROUND(MAX(a.best_avg), 1)           AS max_avg
        FROM applications a
        JOIN programs    p ON p.program_key = a.program_key
        WHERE p.tier = 1
          AND a.decision = 'accepted'
          AND a.best_avg IS NOT NULL
        GROUP BY p.program_key, p.program, a.cycle
        ORDER BY p.program_key, a.cycle
    """)
    cells: list[list] = [headers]
    cells.extend(list(r) for r in rows)
    return {"cells": normalize_rows(cells), "frozen_rows": 1, "header_rows": [0]}


def build_decision_timeline() -> dict:
    headers, rows = query_db("""
        SELECT
            p.program_key,
            p.program,
            SUBSTR(a.decision_date, 1, 7)  AS year_month,
            COUNT(*)                       AS n_decisions,
            SUM(CASE WHEN a.decision = 'accepted' THEN 1 ELSE 0 END) AS n_accepted,
            SUM(CASE WHEN a.decision = 'rejected' THEN 1 ELSE 0 END) AS n_rejected,
            SUM(CASE WHEN a.decision = 'deferred' THEN 1 ELSE 0 END) AS n_deferred
        FROM applications a
        JOIN programs    p ON p.program_key = a.program_key
        WHERE p.tier = 1
          AND a.cycle = '2024-2025'
          AND a.decision_date IS NOT NULL
        GROUP BY p.program_key, p.program, year_month
        ORDER BY p.program_key, year_month
    """)
    cells: list[list] = [headers]
    cells.extend(list(r) for r in rows)
    return {"cells": normalize_rows(cells), "frozen_rows": 1, "header_rows": [0]}


def build_distribution() -> dict:
    """Histograms of accepted averages for Tier-1 programs, with Justin's marker."""
    profile = load_profile()
    justin_mid = profile["grade_12_projected_top6_average"]["midpoint"]

    # Bin: integer percentage points 80-100
    bins = list(range(80, 101))  # 80, 81, ..., 100
    cells: list[list] = []
    cells.append([f"Accepted-average distribution for Tier-1 programs (bin = 1 pct point). Justin's projected midpoint = {justin_mid}%"])
    cells.append([""])

    # Header
    header = ["Avg %"] + ["Justin"]
    headers_q, _ = query_db(
        "SELECT DISTINCT a.program_key FROM applications a JOIN programs p ON p.program_key = a.program_key WHERE p.tier = 1 ORDER BY a.program_key"
    )
    # Get program keys in order
    _, prog_rows = query_db("""
        SELECT a.program_key
        FROM applications a
        JOIN programs p ON p.program_key = a.program_key
        WHERE p.tier = 1
        GROUP BY a.program_key
        ORDER BY a.program_key
    """)
    program_keys = [r[0] for r in prog_rows]

    # Build a count map per program
    counts: dict[str, dict[int, int]] = {pk: {b: 0 for b in bins} for pk in program_keys}
    _, all_rows = query_db("""
        SELECT a.program_key, a.best_avg
        FROM applications a
        JOIN programs p ON p.program_key = a.program_key
        WHERE p.tier = 1 AND a.decision = 'accepted' AND a.best_avg IS NOT NULL
    """)
    for prog_key, avg in all_rows:
        bin_idx = int(avg)
        if bin_idx in counts.get(prog_key, {}):
            counts[prog_key][bin_idx] += 1

    header = ["Avg %"] + program_keys + ["Justin marker"]
    cells.append(header)
    justin_bin = int(round(justin_mid))
    for b in bins:
        row: list[Any] = [f"{b}-{b+1}"]
        for pk in program_keys:
            row.append(counts[pk][b])
        row.append("◀ Justin" if b == justin_bin else "")
        cells.append(row)

    return {"cells": normalize_rows(cells), "frozen_rows": 3, "header_rows": [2]}


def build_data_quality() -> dict:
    cells: list[list] = []
    cells.append(["DATA QUALITY & CAVEATS"])
    cells.append([""])

    # Cycles overview
    cells.append(["Cycles loaded into the analysis:"])
    headers, rows = query_db("""
        SELECT cycle, region, n_rows, n_decisions_mapped, n_universities_mapped, n_programs_mapped, live, refresh_until, fetched_at
        FROM cycles ORDER BY cycle
    """)
    cells.append(headers)
    for r in rows:
        cells.append(list(r))
    cells.append([""])

    # Sample sizes per Tier-1 program
    cells.append(["Sample sizes per Tier-1 target (accepted reports):"])
    _, rows = query_db("""
        SELECT
            p.program_key, p.program,
            COUNT(*) AS n_accepted,
            SUM(CASE WHEN a.decision = 'rejected' THEN 1 ELSE 0 END) AS n_rejected,
            SUM(CASE WHEN a.decision = 'deferred' THEN 1 ELSE 0 END) AS n_deferred,
            SUM(CASE WHEN a.decision = 'waitlisted' THEN 1 ELSE 0 END) AS n_waitlisted
        FROM applications a
        JOIN programs p ON p.program_key = a.program_key
        WHERE p.tier = 1 AND a.decision IS NOT NULL
        GROUP BY p.program_key, p.program
        ORDER BY p.program_key
    """)
    cells.append(["program_key", "program", "n_accepted", "n_rejected", "n_deferred", "n_waitlisted"])
    for r in rows:
        cells.append(list(r))
    cells.append([""])

    # Caveats
    cells.append(["CAVEATS"])
    caveats = [
        ("Self-selection bias",
         "Reddit users overwhelmingly post when they're accepted. Across the 4 cycles the 'accepted' fraction "
         "of reported decisions ranges from ~93% to ~99%. Treat all 'accepted average' numbers as the FLOOR of "
         "what gets in, not as a 50/50 cutoff line."),
        ("OOP small samples",
         "Out-of-province sample sizes are tiny for most programs (4-12 reports per program). The McMaster BHSc "
         "OOP minimum of 97.8% is the strongest signal because all 5 OOP reports cluster tightly above that line. "
         "Other OOP averages are directional only."),
        ("Schema drift across cycles",
         "The 4 Reddit forms used different question sets across years. The 2022-23 form had 10 columns; the "
         "2023-24 form expanded to 21 with separate G11 final, G12 mid/predicted/final fields; the 2024-25 and "
         "2025-26 forms simplified back to 15 columns with a single 'Top 6 Average'. The normalizer maps all of "
         "these to a canonical 'best_avg' field. See workflows/clean_application_data.md for details."),
        ("Live cycle still in progress",
         "The 2025-2026 cycle is still receiving submissions through ~end of May 2026. Numbers from that cycle "
         "are provisional and skew toward earlier-cycle decisions (which tend to be the strongest applicants)."),
        ("McMaster pages are Cloudflare-blocked",
         "Both bhsc.mcmaster.ca and hhsp.healthsci.mcmaster.ca refuse our automated fetches. The McMaster BHSc "
         "and McMaster Life Sci entries in the requirements table are based on public knowledge and marked "
         "confidence=medium. Verify by manually opening those pages in a browser."),
        ("Tier-2 confidence",
         "All 9 Tier-2 entries in the requirements table are confidence=medium. Prerequisite courses are "
         "high-confidence (well-known and stable); specific dates default to the universal Jan 15 OUAC date "
         "and competitive averages are anchored to Reddit data. Spot-check before relying on individual entries."),
        ("Tier-3/4 not yet curated",
         "Tier-3 (Waterloo CS backup variants) and Tier-4 (UAlberta) programs are NOT in the requirements table "
         "yet. They appear in the per-program analysis tab if they have applications data, but their checklist "
         "rows are blank."),
    ]
    for label, body in caveats:
        cells.append([label, body])
    cells.append([""])

    cells.append(["SOURCES"])
    cells.append(["Curated requirements YAML", "config/requirements.yaml (in the repo)"])
    cells.append(["Spreadsheet IDs and form IDs", "config/programs.yaml — `spreadsheets:` section"])
    cells.append(["Normalize QA report", ".tmp/processed/normalize_qa.md"])
    cells.append(["Saved analytical queries", "queries/*.sql"])

    return {"cells": normalize_rows(cells), "frozen_rows": 0, "header_rows": []}


# ──────────────────────────────────────────────────────────────────────────────
# Tab registry — order is preserved by the numeric prefix
# ──────────────────────────────────────────────────────────────────────────────

TABS: list[tuple[str, Callable[[], dict]]] = [
    ("00_Overview",            build_overview),
    ("01_Placement",           build_placement),
    ("02_Per-Program Detail",  build_per_program_detail),
    ("03_Application Checklist", build_application_checklist),
    ("04_YoY Trends",          build_yoy_trends),
    ("05_Decision Timeline",   build_decision_timeline),
    ("06_Distribution",        build_distribution),
    ("07_Data Quality",        build_data_quality),
]

# Map old tab names (pre-placement-tab) → new tab names, so an existing
# dashboard refreshes onto the new layout without leaving stale tabs behind.
TAB_RENAMES: dict[str, str] = {
    "01_Per-Program Detail":    "02_Per-Program Detail",
    "02_Application Checklist": "03_Application Checklist",
    "03_YoY Trends":            "04_YoY Trends",
    "04_Decision Timeline":     "05_Decision Timeline",
    "05_Distribution":          "06_Distribution",
    "06_Data Quality":          "07_Data Quality",
}


# ──────────────────────────────────────────────────────────────────────────────
# Sheet writer — manages add/clear/write/format for each tab
# ──────────────────────────────────────────────────────────────────────────────

def list_existing_sheets(sheets_service, spreadsheet_id: str) -> dict[str, int]:
    """Return {tab_title: sheetId} for the spreadsheet."""
    meta = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title))",
    ).execute()
    return {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}


def ensure_tabs_exist(sheets_service, spreadsheet_id: str, wanted: list[str]) -> dict[str, int]:
    existing = list_existing_sheets(sheets_service, spreadsheet_id)

    # Rename any old tabs to their new names before adding new ones, so content
    # is preserved if we're refreshing onto a new layout.
    rename_requests = []
    for old_name, new_name in TAB_RENAMES.items():
        if old_name in existing and new_name not in existing and new_name in wanted:
            rename_requests.append({
                "updateSheetProperties": {
                    "properties": {"sheetId": existing[old_name], "title": new_name},
                    "fields": "title",
                }
            })
    if rename_requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": rename_requests}
        ).execute()
        existing = list_existing_sheets(sheets_service, spreadsheet_id)

    # Add any missing tabs
    add_requests = []
    for title in wanted:
        if title not in existing:
            add_requests.append({"addSheet": {"properties": {"title": title}}})
    if add_requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": add_requests}
        ).execute()
        existing = list_existing_sheets(sheets_service, spreadsheet_id)

    # Reorder tabs to match the wanted sequence. Google Sheets preserves tab
    # order manually set by the user, so we explicitly set each tab's index.
    reorder_requests = []
    for i, title in enumerate(wanted):
        if title in existing:
            reorder_requests.append({
                "updateSheetProperties": {
                    "properties": {"sheetId": existing[title], "index": i},
                    "fields": "index",
                }
            })
    if reorder_requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": reorder_requests}
        ).execute()
        existing = list_existing_sheets(sheets_service, spreadsheet_id)

    return existing


def delete_default_sheet1(sheets_service, spreadsheet_id: str, existing: dict[str, int],
                          wanted: list[str]) -> None:
    """Remove the default 'Sheet1' tab if it isn't in our wanted list."""
    if "Sheet1" in existing and "Sheet1" not in wanted:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"deleteSheet": {"sheetId": existing["Sheet1"]}}]}
        ).execute()


def write_tab(sheets_service, spreadsheet_id: str, tab_title: str, sheet_id_int: int,
              cells: list[list], frozen_rows: int, header_rows: list[int]) -> None:
    # Clear existing values
    sheets_service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range=f"'{tab_title}'"
    ).execute()

    # Write fresh values
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_title}'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": cells},
    ).execute()

    # Apply formatting: freeze + bold header rows
    requests: list[dict] = []
    if frozen_rows > 0:
        requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id_int,
                    "gridProperties": {"frozenRowCount": frozen_rows},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        })
    for hr in header_rows:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id_int,
                    "startRowIndex": hr,
                    "endRowIndex": hr + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": {"red": 0.92, "green": 0.92, "blue": 0.95},
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })
    if requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create", action="store_true",
                        help="Force creating a new spreadsheet, ignoring any cached ID")
    parser.add_argument("--print-url", action="store_true",
                        help="Just print the cached spreadsheet URL and exit")
    args = parser.parse_args()

    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found. Run tools/build_sqlite.py first.")
    if not PROFILE_PATH.exists():
        sys.exit(f"ERROR: {PROFILE_PATH} not found.")

    if args.print_url:
        state = load_state()
        sheet_id = state.get("sheet_id")
        if not sheet_id:
            sys.exit("No cached dashboard sheet ID. Run without --print-url to create one.")
        print(f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
        return 0

    print("Authorizing...")
    sheets_service = get_sheets_service()

    print("Resolving dashboard spreadsheet...")
    spreadsheet_id, was_created = get_or_create_spreadsheet(sheets_service, force_create=args.create)
    if was_created:
        print(f"  Created new spreadsheet: {spreadsheet_id}")
    else:
        print(f"  Refreshing existing spreadsheet: {spreadsheet_id}")

    wanted_titles = [t for t, _ in TABS]
    existing = ensure_tabs_exist(sheets_service, spreadsheet_id, wanted_titles)
    delete_default_sheet1(sheets_service, spreadsheet_id, existing, wanted_titles)
    existing = list_existing_sheets(sheets_service, spreadsheet_id)

    print("\nBuilding tabs...")
    for tab_title, builder in TABS:
        try:
            tab = builder()
        except Exception as e:
            print(f"  FAIL  {tab_title}: {type(e).__name__}: {e}")
            raise
        sheet_id_int = existing[tab_title]
        write_tab(
            sheets_service, spreadsheet_id, tab_title, sheet_id_int,
            cells=tab["cells"],
            frozen_rows=tab.get("frozen_rows", 0),
            header_rows=tab.get("header_rows", []),
        )
        n_rows = len(tab["cells"])
        n_cols = max((len(r) for r in tab["cells"]), default=0)
        print(f"  OK    {tab_title:30}  {n_rows:>4} rows x {n_cols:>3} cols")

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    print()
    print(f"Done. Open the dashboard at:")
    print(f"  {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
