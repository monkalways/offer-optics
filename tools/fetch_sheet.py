"""Download a Google Sheet tab as CSV.

Reads spreadsheet IDs from config/programs.yaml and writes to .tmp/raw/{cycle}_responses.csv.

Usage:
    python tools/fetch_sheet.py --cycle 2022-2023
    python tools/fetch_sheet.py --cycle all
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml

from google_auth import get_sheets_service  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROGRAMS_YAML = PROJECT_ROOT / "config" / "programs.yaml"
RAW_DIR = PROJECT_ROOT / ".tmp" / "raw"


def _load_configs() -> list[dict]:
    data = yaml.safe_load(PROGRAMS_YAML.read_text(encoding="utf-8"))
    return data.get("spreadsheets", [])


def _resolve_tab_title(sheets, sheet_id: str, gid: int | None) -> tuple[str, str]:
    """Return (spreadsheet_title, tab_title) for the requested gid (or first tab)."""
    meta = sheets.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="properties(title),sheets(properties(sheetId,title))",
    ).execute()
    title = meta["properties"]["title"]
    tabs = meta["sheets"]
    if gid is not None:
        tab = next((t for t in tabs if t["properties"]["sheetId"] == gid), None)
        if tab is None:
            raise RuntimeError(
                f"gid {gid} not found in spreadsheet '{title}'. "
                f"Available: {[(t['properties']['sheetId'], t['properties']['title']) for t in tabs]}"
            )
    else:
        tab = tabs[0]
    return title, tab["properties"]["title"]


def fetch_one(cfg: dict) -> Path:
    cycle = cfg["cycle"]
    sheet_id = cfg["sheet_id"]
    gid = cfg.get("gid")

    sheets = get_sheets_service()
    spreadsheet_title, tab_title = _resolve_tab_title(sheets, sheet_id, gid)

    # Pull every cell in the tab. UNFORMATTED_VALUE preserves numbers as numbers
    # (so a "95.5" doesn't get auto-truncated by display formatting), and
    # FORMATTED_STRING for dates would lose ISO precision — we'll handle date parsing
    # downstream. Use FORMATTED_VALUE for now so we get whatever the form recorded.
    resp = sheets.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{tab_title}'",
        valueRenderOption="FORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    values = resp.get("values", [])

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{cycle}_responses.csv"
    # Note: gspread/Sheets API returns ragged rows (rows shorter than the widest row
    # are not padded). Pad to the max width so the CSV is rectangular.
    max_w = max((len(r) for r in values), default=0)
    padded = [r + [""] * (max_w - len(r)) for r in values]

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(padded)

    print(f"  {cycle}: wrote {len(padded)} rows x {max_w} cols -> {out_path.relative_to(PROJECT_ROOT)}")
    print(f"           source: '{spreadsheet_title}' / '{tab_title}'")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", default="all", help="Cycle key (e.g. '2022-2023') or 'all'")
    args = parser.parse_args()

    configs = _load_configs()
    if args.cycle != "all":
        configs = [c for c in configs if c["cycle"] == args.cycle]
        if not configs:
            sys.exit(f"ERROR: cycle '{args.cycle}' not found in {PROGRAMS_YAML}")

    print(f"Fetching {len(configs)} spreadsheet(s)...\n")
    for cfg in configs:
        fetch_one(cfg)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
