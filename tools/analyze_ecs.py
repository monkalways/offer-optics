"""Keyword-based EC categorization for the Reddit application dataset.

Scans supp_app_notes, extracurriculars, and comments fields from the
applications table and tags each row with EC categories defined in
config/ec_categories.yaml. Writes results to:

  - SQLite `ec_categories` table (dropped + recreated on each run)
  - Per-program summary JSONs in .tmp/analysis/ec_{program_key}.json

Usage:
    python tools/analyze_ecs.py
    python tools/analyze_ecs.py --print-summary
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / ".tmp" / "applications.sqlite"
EC_CONFIG_PATH = PROJECT_ROOT / "config" / "ec_categories.yaml"
PROFILE_PATH = PROJECT_ROOT / "config" / "justin_profile.json"
ANALYSIS_DIR = PROJECT_ROOT / ".tmp" / "analysis"

TIER1_PROGRAMS = ["mcmaster_bhsc", "queens_bhsc", "waterloo_cs"]


def load_ec_config() -> dict:
    return yaml.safe_load(EC_CONFIG_PATH.read_text(encoding="utf-8"))


def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def categorize_text(text: str, categories: list[dict]) -> list[str]:
    if not text:
        return []
    text_lower = text.lower()
    matched = []
    for cat in categories:
        for kw in cat["keywords"]:
            if kw.lower() in text_lower:
                matched.append(cat["key"])
                break
    return matched


def build_ec_text(row: dict) -> str:
    parts = []
    for field in ("supp_app_notes", "extracurriculars", "comments", "supp_app_raw"):
        val = row.get(field)
        if val and str(val).strip():
            parts.append(str(val).strip())
    return " ".join(parts)


def select_sample_quotes(conn: sqlite3.Connection, program_key: str,
                         max_quotes: int = 5) -> list[str]:
    rows = conn.execute("""
        SELECT supp_app_notes, extracurriculars
        FROM applications
        WHERE program_key = ?
          AND decision = 'accepted'
          AND (
            (supp_app_notes IS NOT NULL AND LENGTH(TRIM(supp_app_notes)) > 20)
            OR (extracurriculars IS NOT NULL AND LENGTH(TRIM(extracurriculars)) > 20)
          )
        ORDER BY RANDOM()
        LIMIT ?
    """, (program_key, max_quotes * 3)).fetchall()

    quotes = []
    for supp_notes, ecs in rows:
        text = (supp_notes or "").strip()
        if len(text) < 20:
            text = (ecs or "").strip()
        if len(text) >= 20 and text not in quotes:
            if len(text) > 250:
                text = text[:247] + "..."
            quotes.append(text)
        if len(quotes) >= max_quotes:
            break
    return quotes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found")

    ec_config = load_ec_config()
    categories = ec_config["categories"]
    justin_cats = set(ec_config.get("justin_categories", []))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if args.print_summary:
        try:
            rows = conn.execute("SELECT * FROM ec_program_summary ORDER BY program_key").fetchall()
        except sqlite3.OperationalError:
            print("ec_program_summary table does not exist yet. Run without --print-summary first.")
            return 1
        for r in rows:
            print(f"{r['program_key']:28} n_with_ec={r['n_with_ec_data']:>3}  "
                  f"n_accepted={r['n_accepted_total']:>3}  coverage={r['coverage_pct']:.0f}%")
        return 0

    try:
        # Fetch all application rows with their EC-related fields
        app_rows = conn.execute("""
            SELECT source_row, cycle, program_key, decision,
                   supp_app_notes, extracurriculars, comments, supp_app_raw
            FROM applications
            WHERE program_key IS NOT NULL
        """).fetchall()

        print(f"Processing {len(app_rows)} rows with {len(categories)} EC categories...")

        # Categorize each row
        ec_rows: list[dict] = []
        for row in app_rows:
            text = build_ec_text(dict(row))
            if not text.strip():
                continue
            matched = categorize_text(text, categories)
            if matched:
                ec_rows.append({
                    "source_row": row["source_row"],
                    "cycle": row["cycle"],
                    "program_key": row["program_key"],
                    "decision": row["decision"],
                    "categories_json": json.dumps(matched),
                    "n_categories": len(matched),
                })

        print(f"  {len(ec_rows)} rows matched at least one EC category")

        # Write ec_categories table
        conn.executescript("""
            DROP TABLE IF EXISTS ec_categories;
            CREATE TABLE ec_categories (
                source_row      INTEGER,
                cycle           TEXT,
                program_key     TEXT,
                decision        TEXT,
                categories_json TEXT,
                n_categories    INTEGER
            );
            CREATE INDEX idx_ec_program ON ec_categories(program_key);
            CREATE INDEX idx_ec_decision ON ec_categories(program_key, decision);
        """)
        conn.executemany(
            "INSERT INTO ec_categories VALUES (:source_row, :cycle, :program_key, "
            ":decision, :categories_json, :n_categories)",
            ec_rows,
        )

        # Build per-program summaries
        conn.executescript("DROP TABLE IF EXISTS ec_program_summary;")
        conn.execute("""
            CREATE TABLE ec_program_summary (
                program_key         TEXT PRIMARY KEY,
                n_with_ec_data      INTEGER,
                n_accepted_total    INTEGER,
                coverage_pct        REAL,
                category_freq_json  TEXT,
                top_categories_json TEXT,
                sample_quotes_json  TEXT,
                justin_matched_json TEXT,
                justin_missing_json TEXT,
                justin_match_pct    REAL
            )
        """)

        cat_keys = [c["key"] for c in categories]
        cat_labels = {c["key"]: c["label"] for c in categories}

        for prog_key in TIER1_PROGRAMS:
            # Count accepted total
            (n_accepted_total,) = conn.execute(
                "SELECT COUNT(*) FROM applications WHERE program_key=? AND decision='accepted'",
                (prog_key,)
            ).fetchone()

            # Count rows with EC data
            ec_accepted = conn.execute(
                "SELECT categories_json FROM ec_categories WHERE program_key=? AND decision='accepted'",
                (prog_key,)
            ).fetchall()
            n_with_ec = len(ec_accepted)

            # Category frequencies among accepted
            freq: Counter = Counter()
            for (cj,) in ec_accepted:
                for cat in json.loads(cj):
                    freq[cat] += 1

            # Sort by frequency
            freq_dict = {cat_labels.get(k, k): v for k, v in freq.most_common()}
            top_cats = [cat_labels.get(k, k) for k, _ in freq.most_common(5)]

            # Sample quotes
            quotes = select_sample_quotes(conn, prog_key, max_quotes=5)

            # Justin alignment
            present_cats = {k for k in cat_keys if freq.get(k, 0) > 0}
            justin_matched = sorted(justin_cats & present_cats)
            justin_missing = sorted(present_cats - justin_cats)
            match_pct = (
                len(justin_matched) / len(present_cats) * 100 if present_cats else 0
            )

            coverage = n_with_ec / n_accepted_total * 100 if n_accepted_total else 0

            conn.execute(
                "INSERT INTO ec_program_summary VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    prog_key,
                    n_with_ec,
                    n_accepted_total,
                    round(coverage, 1),
                    json.dumps(freq_dict, ensure_ascii=False),
                    json.dumps(top_cats, ensure_ascii=False),
                    json.dumps(quotes, ensure_ascii=False),
                    json.dumps([cat_labels.get(k, k) for k in justin_matched], ensure_ascii=False),
                    json.dumps([cat_labels.get(k, k) for k in justin_missing], ensure_ascii=False),
                    round(match_pct, 1),
                ),
            )

            # Also write per-program JSON
            ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
            summary = {
                "program_key": prog_key,
                "n_with_ec_data": n_with_ec,
                "n_accepted_total": n_accepted_total,
                "coverage_pct": round(coverage, 1),
                "category_frequencies": freq_dict,
                "top_categories": top_cats,
                "sample_quotes": quotes,
                "justin_alignment": {
                    "matched": [cat_labels.get(k, k) for k in justin_matched],
                    "missing": [cat_labels.get(k, k) for k in justin_missing],
                    "match_rate_pct": round(match_pct, 1),
                },
            }
            (ANALYSIS_DIR / f"ec_{prog_key}.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            print(f"  {prog_key:28}  n_ec={n_with_ec:>3}/{n_accepted_total}  "
                  f"coverage={coverage:.0f}%  top: {', '.join(top_cats[:3])}")

        conn.commit()
    finally:
        conn.close()

    print(f"\nWrote ec_categories table + {len(TIER1_PROGRAMS)} summary JSONs to .tmp/analysis/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
