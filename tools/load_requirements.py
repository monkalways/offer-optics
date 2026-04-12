"""Load config/requirements.yaml into the SQLite `requirements` table.

Idempotent — drops and recreates all rows on each run. Reads from the curated
YAML (the source of truth) and validates against config/programs.yaml so we
catch typos in program_key.

Usage:
    python tools/load_requirements.py
    python tools/load_requirements.py --print-summary
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQ_YAML = PROJECT_ROOT / "config" / "requirements.yaml"
PROGRAMS_YAML = PROJECT_ROOT / "config" / "programs.yaml"
DB_PATH = PROJECT_ROOT / ".tmp" / "applications.sqlite"


# Columns in the `requirements` table (must match the CREATE TABLE in build_sqlite.py
# plus any additional columns we add here).
SCHEMA_COLUMNS = [
    "program_key", "tier", "source_url", "curated_on", "confidence", "curator_notes",
    "application_deadline_ouac", "application_deadline_supp", "document_deadline",
    "decision_release_window",
    "supp_app_required", "supp_app_type", "supp_app_url", "supp_app_notes",
    "casper_required", "casper_format",
    "interview_required", "interview_format",
    "references_required", "references_count",
    "min_average_competitive", "prereq_courses_json", "prereq_notes",
    "oop_eligible", "oop_notes",
    "application_fee_cad", "notes",
    "loaded_at",
]


def load_known_program_keys() -> set[str]:
    data = yaml.safe_load(PROGRAMS_YAML.read_text(encoding="utf-8"))
    return {p["key"] for p in data.get("programs", [])}


def load_requirements_yaml() -> tuple[list[dict], dict]:
    raw = yaml.safe_load(REQ_YAML.read_text(encoding="utf-8"))
    return raw.get("requirements", []), raw


def to_int_bool(v) -> int | None:
    if v is None:
        return None
    return 1 if v else 0


def iso(v) -> str | None:
    """Coerce a YAML-parsed date/datetime to an ISO string. Pass through other types."""
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def row_from_entry(entry: dict, loaded_at: str) -> dict:
    """Project a YAML entry to the SQLite row schema. Coerces dates to ISO strings."""
    return {
        "program_key":               entry.get("program_key"),
        "tier":                      entry.get("tier"),
        "source_url":                entry.get("source_url"),
        "curated_on":                iso(entry.get("curated_on")),
        "confidence":                entry.get("confidence"),
        "curator_notes":             entry.get("curator_notes"),
        "application_deadline_ouac": iso(entry.get("application_deadline_ouac")),
        "application_deadline_supp": iso(entry.get("application_deadline_supp")),
        "document_deadline":         iso(entry.get("document_deadline")),
        "decision_release_window":   entry.get("decision_release_window"),
        "supp_app_required":         to_int_bool(entry.get("supp_app_required")),
        "supp_app_type":             entry.get("supp_app_type"),
        "supp_app_url":              entry.get("supp_app_url"),
        "supp_app_notes":            entry.get("supp_app_notes"),
        "casper_required":           to_int_bool(entry.get("casper_required")),
        "casper_format":             entry.get("casper_format"),
        "interview_required":        to_int_bool(entry.get("interview_required")),
        "interview_format":          entry.get("interview_format"),
        "references_required":       to_int_bool(entry.get("references_required")),
        "references_count":          entry.get("references_count"),
        "min_average_competitive":   entry.get("min_average_competitive"),
        "prereq_courses_json":       json.dumps(entry.get("prereq_courses", []), ensure_ascii=False),
        "prereq_notes":              entry.get("prereq_notes"),
        "oop_eligible":              to_int_bool(entry.get("oop_eligible")),
        "oop_notes":                 entry.get("oop_notes"),
        "application_fee_cad":       entry.get("application_fee_cad"),
        "notes":                     entry.get("notes"),
        "loaded_at":                 loaded_at,
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Recreate the requirements table with our full schema (drops existing)."""
    conn.executescript("""
        DROP TABLE IF EXISTS requirements;
        CREATE TABLE requirements (
            program_key                TEXT PRIMARY KEY,
            tier                       INTEGER,
            source_url                 TEXT,
            curated_on                 TEXT,
            confidence                 TEXT,
            curator_notes              TEXT,
            application_deadline_ouac  TEXT,
            application_deadline_supp  TEXT,
            document_deadline          TEXT,
            decision_release_window    TEXT,
            supp_app_required          INTEGER,
            supp_app_type              TEXT,
            supp_app_url               TEXT,
            supp_app_notes             TEXT,
            casper_required            INTEGER,
            casper_format              TEXT,
            interview_required         INTEGER,
            interview_format           TEXT,
            references_required        INTEGER,
            references_count           INTEGER,
            min_average_competitive    REAL,
            prereq_courses_json        TEXT,
            prereq_notes               TEXT,
            oop_eligible               INTEGER,
            oop_notes                  TEXT,
            application_fee_cad        INTEGER,
            notes                      TEXT,
            loaded_at                  TEXT
        );
        CREATE INDEX idx_req_tier ON requirements(tier);
        CREATE INDEX idx_req_confidence ON requirements(confidence);
    """)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-summary", action="store_true",
                        help="Print row counts and per-confidence breakdown without re-loading")
    args = parser.parse_args()

    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found. Run tools/build_sqlite.py first.")

    if args.print_summary:
        conn = sqlite3.connect(DB_PATH)
        try:
            (n,) = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()
            print(f"requirements: {n} rows")
            print("\nBy tier:")
            for row in conn.execute("SELECT tier, COUNT(*) FROM requirements GROUP BY tier ORDER BY tier"):
                print(f"  tier {row[0]}: {row[1]}")
            print("\nBy confidence:")
            for row in conn.execute("SELECT confidence, COUNT(*) FROM requirements GROUP BY confidence"):
                print(f"  {row[0]}: {row[1]}")
        finally:
            conn.close()
        return 0

    if not REQ_YAML.exists():
        sys.exit(f"ERROR: {REQ_YAML} not found")

    entries, _full = load_requirements_yaml()
    if not entries:
        sys.exit(f"ERROR: no requirements entries in {REQ_YAML}")

    known_keys = load_known_program_keys()
    bad_keys = [e.get("program_key") for e in entries if e.get("program_key") not in known_keys]
    if bad_keys:
        sys.exit(f"ERROR: requirements YAML references program keys not in programs.yaml: {bad_keys}")

    loaded_at = datetime.now().isoformat(timespec="seconds")
    rows = [row_from_entry(e, loaded_at) for e in entries]

    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_schema(conn)
        placeholders = ", ".join(":" + c for c in SCHEMA_COLUMNS)
        cols = ", ".join(SCHEMA_COLUMNS)
        conn.executemany(f"INSERT INTO requirements ({cols}) VALUES ({placeholders})", rows)
        conn.commit()

        # Summary
        print(f"Loaded {len(rows)} requirement entries from {REQ_YAML.relative_to(PROJECT_ROOT)}")
        print()
        print("By tier:")
        for row in conn.execute("SELECT tier, COUNT(*) FROM requirements GROUP BY tier ORDER BY tier"):
            print(f"  tier {row[0]}: {row[1]}")
        print()
        print("By confidence:")
        for row in conn.execute("SELECT confidence, COUNT(*) FROM requirements GROUP BY confidence"):
            print(f"  {row[0]}: {row[1]}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
