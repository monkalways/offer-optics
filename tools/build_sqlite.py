"""Build the SQLite query layer from the normalized parquet.

Reads .tmp/processed/applications.parquet (written by normalize_data.py) and
config/programs.yaml, then writes .tmp/applications.sqlite with these tables:

  applications  — every normalized application row, one per (student × prog × decision)
  programs      — canonical program registry from programs.yaml
  cycles        — per-cycle metadata (region, source sheet, refresh status, n rows)
  requirements  — empty placeholder; populated later by tools/scrape_program_requirements.py

Indexes are created on the columns most-used by the saved queries in queries/.

Usage:
    python tools/build_sqlite.py
    python tools/build_sqlite.py --print-summary
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARQUET_PATH = PROJECT_ROOT / ".tmp" / "processed" / "applications.parquet"
DB_PATH = PROJECT_ROOT / ".tmp" / "applications.sqlite"
PROGRAMS_YAML = PROJECT_ROOT / "config" / "programs.yaml"


# Columns we expose in the `applications` table. Order matters for readability
# in DB Browser. We drop a few *_raw columns we don't need at query time
# (the parquet still has them for traceability).
APPLICATION_COLUMNS = [
    "cycle", "region", "source_row",
    "timestamp", "timestamp_iso",
    "university_key", "university_raw",
    "program_key", "program_raw", "ouac_code",
    "decision", "decision_raw",
    "best_avg", "acceptance_avg",
    "g11_final", "g12_midterm", "g12_predicted", "g12_final",
    "applied_date", "decision_date",
    "applicant_type", "applicant_type_raw",
    "province", "province_raw",
    "citizenship", "citizenship_raw",
    "country_raw",
    "supp_app_raw", "supp_app_notes",
    "student_response_raw",
    "extracurriculars", "test_scores_raw", "scholarship_raw",
    "reddit_username", "discord_username", "comments",
]


def load_programs_table() -> pd.DataFrame:
    data = yaml.safe_load(PROGRAMS_YAML.read_text(encoding="utf-8"))
    rows = []
    for p in data.get("programs", []):
        rows.append({
            "program_key": p["key"],
            "tier": p.get("tier"),
            "university": p.get("university"),
            "university_key": p.get("university_key"),
            "program": p.get("program"),
            "official_url": p.get("official_url"),
            "match_patterns": " | ".join(p.get("match_patterns", [])),
        })
    return pd.DataFrame(rows)


def load_cycles_table(apps_df: pd.DataFrame) -> pd.DataFrame:
    data = yaml.safe_load(PROGRAMS_YAML.read_text(encoding="utf-8"))
    sheets = data.get("spreadsheets", [])
    by_cycle: dict[str, dict] = {s["cycle"]: s for s in sheets}
    fetched_at = datetime.now().isoformat(timespec="seconds")
    rows = []
    for cycle, sub in apps_df.groupby("cycle", sort=True):
        cfg = by_cycle.get(cycle, {})
        rows.append({
            "cycle": cycle,
            "region": cfg.get("region"),
            "sheet_id": cfg.get("sheet_id"),
            "gid": cfg.get("gid"),
            "live": int(bool(cfg.get("live"))),
            "refresh_until": cfg.get("refresh_until"),
            "n_rows": int(len(sub)),
            "n_decisions_mapped": int(sub["decision"].notna().sum()),
            "n_universities_mapped": int(sub["university_key"].notna().sum()),
            "n_programs_mapped": int(sub["program_key"].notna().sum()),
            "fetched_at": fetched_at,
        })
    return pd.DataFrame(rows)


def build(verbose: bool = True) -> Path:
    if not PARQUET_PATH.exists():
        sys.exit(f"ERROR: {PARQUET_PATH} not found. Run tools/normalize_data.py first.")

    apps = pd.read_parquet(PARQUET_PATH)
    # Restrict to known columns and add any missing as null (so schema is stable
    # even if a future cycle introduces new fields)
    for col in APPLICATION_COLUMNS:
        if col not in apps.columns:
            apps[col] = None
    apps_out = apps[APPLICATION_COLUMNS].copy()

    programs_df = load_programs_table()
    cycles_df = load_cycles_table(apps)

    # Open fresh DB
    if DB_PATH.exists():
        DB_PATH.unlink()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    try:
        # Use pandas to_sql for the bulk load. We follow up with explicit
        # CREATE INDEX statements because pandas doesn't create indexes.
        apps_out.to_sql("applications", conn, index=False)
        programs_df.to_sql("programs", conn, index=False)
        cycles_df.to_sql("cycles", conn, index=False)

        # Empty placeholder for the requirements tracker (Step 5)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS requirements (
                program_key            TEXT PRIMARY KEY,
                application_deadline   TEXT,
                document_deadline      TEXT,
                supp_app_required      INTEGER,
                supp_app_deadline      TEXT,
                supp_app_notes         TEXT,
                casper_required        INTEGER,
                interview_required     INTEGER,
                interview_format       TEXT,
                references_required    INTEGER,
                prereq_courses         TEXT,
                oop_notes              TEXT,
                application_fee        TEXT,
                source_url             TEXT,
                fetched_at             TEXT
            );
        """)

        # Indexes — focused on the joins/filters the saved queries use
        index_sql = [
            "CREATE INDEX idx_apps_cycle ON applications (cycle);",
            "CREATE INDEX idx_apps_region ON applications (region);",
            "CREATE INDEX idx_apps_university_key ON applications (university_key);",
            "CREATE INDEX idx_apps_program_key ON applications (program_key);",
            "CREATE INDEX idx_apps_decision ON applications (decision);",
            "CREATE INDEX idx_apps_program_decision ON applications (program_key, decision);",
            "CREATE INDEX idx_apps_province ON applications (province);",
            "CREATE INDEX idx_apps_decision_date ON applications (decision_date);",
            "CREATE INDEX idx_progs_tier ON programs (tier);",
            "CREATE INDEX idx_progs_university_key ON programs (university_key);",
        ]
        for stmt in index_sql:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()

    if verbose:
        print(f"  Wrote {DB_PATH.relative_to(PROJECT_ROOT)}")
        print(f"    applications:  {len(apps_out):,} rows")
        print(f"    programs:      {len(programs_df):,} rows")
        print(f"    cycles:        {len(cycles_df):,} rows")
        print(f"    requirements:  0 rows (placeholder)")
    return DB_PATH


def print_summary() -> None:
    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found. Run without --print-summary first.")
    conn = sqlite3.connect(DB_PATH)
    try:
        print("\nTables:")
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            (n,) = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()
            print(f"  {name:14}  {n:>6,} rows")

        print("\nIndexes:")
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ):
            print(f"  {name}")

        print("\nCycles overview:")
        for row in conn.execute(
            "SELECT cycle, region, n_rows, n_programs_mapped, live, refresh_until "
            "FROM cycles ORDER BY cycle"
        ):
            print(f"  {row[0]:14}  region={row[1] or '?':3}  rows={row[2]:>5}  "
                  f"prog_mapped={row[3]:>5}  live={'Y' if row[4] else 'N'}  "
                  f"refresh_until={row[5] or '-'}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-summary", action="store_true",
                        help="Print table/index summary of the existing DB instead of rebuilding")
    args = parser.parse_args()

    if args.print_summary:
        print_summary()
        return 0

    print("Building SQLite query layer...")
    build()
    print()
    print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
