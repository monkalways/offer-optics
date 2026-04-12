"""Execute a saved SQL query against .tmp/applications.sqlite and print results.

Supports a single :param substitution via --param NAME=VALUE for queries that
use a `:name` placeholder. Multiple params can be passed by repeating --param.

Usage:
    python tools/run_query.py queries/cutoffs_per_program.sql
    python tools/run_query.py queries/per_program_detail.sql --param program=mcmaster_bhsc
    python tools/run_query.py queries/per_program_detail.sql --param program=waterloo_cs --csv
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

# Force UTF-8 stdout so em-dashes / accented characters render on Windows cmd
# (Python 3.7+; no-op on already-UTF-8 terminals).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / ".tmp" / "applications.sqlite"


def parse_params(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            sys.exit(f"ERROR: --param values must be NAME=VALUE (got {item!r})")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _format_table(rows: list[tuple], headers: list[str]) -> str:
    if not rows:
        return "(no rows)\n"

    def cell(v) -> str:
        if v is None:
            return ""
        if isinstance(v, float):
            # Trim trailing zeros for readability
            if v == int(v):
                return f"{int(v)}"
            return f"{v:.4g}"
        return str(v)

    str_rows = [[cell(v) for v in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in str_rows:
        for i, v in enumerate(row):
            widths[i] = max(widths[i], len(v))

    def fmt_row(values):
        return "  " + "  ".join(v.ljust(widths[i]) for i, v in enumerate(values))

    out = []
    out.append(fmt_row(headers))
    out.append(fmt_row(["-" * w for w in widths]))
    for r in str_rows:
        out.append(fmt_row(r))
    out.append("")
    out.append(f"  ({len(rows)} row{'s' if len(rows) != 1 else ''})")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query_file", help="Path to a .sql file")
    parser.add_argument("--param", action="append", default=[],
                        help="Substitution for a :name placeholder, e.g. --param program=mcmaster_bhsc")
    parser.add_argument("--csv", action="store_true", help="Print as CSV instead of a table")
    args = parser.parse_args()

    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found. Run tools/build_sqlite.py first.")

    sql_path = Path(args.query_file)
    if not sql_path.exists():
        sys.exit(f"ERROR: query file {sql_path} not found")

    sql = sql_path.read_text(encoding="utf-8")
    params = parse_params(args.param)

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
        except sqlite3.Error as e:
            sys.exit(f"SQL error in {sql_path}: {e}")
        rows = cur.fetchall()
        headers = [d[0] for d in cur.description] if cur.description else []
    finally:
        conn.close()

    if args.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(rows)
    else:
        print(f"\n# {sql_path.name}")
        if params:
            print(f"# params: {params}")
        print()
        print(_format_table(rows, headers))
    return 0


if __name__ == "__main__":
    sys.exit(main())
