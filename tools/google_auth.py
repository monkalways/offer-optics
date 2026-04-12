"""Shared Google API authentication helper.

Loads OAuth credentials from `credentials.json` (Desktop client), runs the
browser-based consent flow on first use, and caches the refresh token in
`token.json` for future runs.

Usage:
    from tools.google_auth import get_gspread_client, get_drive_service, get_sheets_service

CLI smoke tests:
    python tools/google_auth.py --whoami
    python tools/google_auth.py --probe-sheets        # try a 1-cell read on every cycle
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import gspread
import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"
PROGRAMS_YAML = PROJECT_ROOT / "config" / "programs.yaml"

# Scopes:
#   - spreadsheets:    read + write (Step 6 dashboard refresh writes to a sheet we own)
#   - drive.file:      create/manage files this app creates (used by build_dashboard.py)
#   - forms.body.readonly: read Google Form question structure (Step 2 inspect_form.py)
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/forms.body.readonly",
]


def _validate_credentials_file() -> None:
    """Fail loudly if credentials.json isn't a Desktop OAuth client."""
    if not CREDENTIALS_PATH.exists():
        sys.exit(
            f"ERROR: {CREDENTIALS_PATH} not found.\n"
            "Download a Desktop-app OAuth client from Google Cloud Console "
            "and save it as credentials.json in the project root."
        )
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: credentials.json is not valid JSON: {e}")
    if "installed" not in data:
        kind = "service account" if data.get("type") == "service_account" else "web client or unknown"
        sys.exit(
            f"ERROR: credentials.json is a {kind}, not a Desktop OAuth client.\n"
            "Re-create the OAuth client in Google Cloud Console and choose "
            "Application type = 'Desktop app'."
        )


def get_credentials() -> Credentials:
    """Return valid OAuth credentials, running the browser flow if needed."""
    _validate_credentials_file()

    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception as e:
            print(f"WARN: failed to load existing token.json ({e}); re-auth required.")
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            return creds
        except Exception as e:
            print(f"WARN: token refresh failed ({e}); falling back to full re-auth.")

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    return creds


def get_gspread_client() -> gspread.Client:
    return gspread.authorize(get_credentials())


def get_drive_service():
    return build("drive", "v3", credentials=get_credentials(), cache_discovery=False)


def get_sheets_service():
    return build("sheets", "v4", credentials=get_credentials(), cache_discovery=False)


def get_forms_service():
    return build("forms", "v1", credentials=get_credentials(), cache_discovery=False)


def whoami() -> str:
    """Return the email address of the authorized user via the Drive 'about' endpoint."""
    drive = get_drive_service()
    about = drive.about().get(fields="user(emailAddress,displayName)").execute()
    user = about.get("user", {})
    return f"{user.get('displayName', '?')} <{user.get('emailAddress', '?')}>"


def _load_spreadsheet_configs() -> list[dict]:
    if not PROGRAMS_YAML.exists():
        sys.exit(f"ERROR: {PROGRAMS_YAML} not found")
    data = yaml.safe_load(PROGRAMS_YAML.read_text(encoding="utf-8"))
    return data.get("spreadsheets", [])


def probe_sheets() -> int:
    """Attempt a 1-cell read on every configured spreadsheet. Returns exit code."""
    sheets = get_sheets_service()
    configs = _load_spreadsheet_configs()

    print(f"\nProbing {len(configs)} spreadsheets with the authorized account...\n")
    failures = 0
    for cfg in configs:
        cycle = cfg["cycle"]
        sheet_id = cfg["sheet_id"]
        gid = cfg.get("gid")
        label = f"  {cycle}  ({sheet_id[:10]}...)"
        try:
            # Look up the sheet's metadata first so we know the tab title for the gid.
            meta = sheets.spreadsheets().get(
                spreadsheetId=sheet_id,
                fields="properties(title),sheets(properties(sheetId,title,gridProperties))",
            ).execute()
            title = meta["properties"]["title"]
            tabs = meta["sheets"]
            if gid is not None:
                tab = next((t for t in tabs if t["properties"]["sheetId"] == gid), None)
                if tab is None:
                    raise RuntimeError(f"gid {gid} not found in spreadsheet (tabs: "
                                       f"{[t['properties']['sheetId'] for t in tabs]})")
            else:
                tab = tabs[0]
            tab_title = tab["properties"]["title"]
            rows = tab["properties"]["gridProperties"].get("rowCount", "?")
            cols = tab["properties"]["gridProperties"].get("columnCount", "?")

            # Now do an actual single-cell read to confirm read permission, not just metadata.
            cell = sheets.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=f"'{tab_title}'!A1",
            ).execute()
            a1 = (cell.get("values") or [[""]])[0][0] if cell.get("values") else ""

            print(f"  OK   {cycle}  -> '{title}'")
            print(f"           tab '{tab_title}'  ({rows}x{cols})  A1={a1!r}")
        except HttpError as e:
            failures += 1
            print(f"  FAIL {cycle}  HTTP {e.resp.status}: {e._get_reason() if hasattr(e, '_get_reason') else e}")
        except Exception as e:
            failures += 1
            print(f"  FAIL {cycle}  {type(e).__name__}: {e}")

    print()
    if failures:
        print(f"{failures} spreadsheet(s) failed. The authorized account may need view access.")
        print("Open each failing sheet in your browser while logged in as the same Google account,")
        print("OR ask the sheet owner to share it with the authorized email.")
        return 1
    print("All spreadsheets readable.")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--whoami", action="store_true", help="Print authorized user email")
    parser.add_argument("--probe-sheets", action="store_true",
                        help="Try a single-cell read on every configured spreadsheet")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not (args.whoami or args.probe_sheets):
        # Default behavior: just trigger / refresh auth and report identity.
        args.whoami = True

    if args.whoami:
        print(f"Authorized as: {whoami()}")
        print(f"Token cached at: {TOKEN_PATH}")
    if args.probe_sheets:
        return probe_sheets()
    return 0


if __name__ == "__main__":
    sys.exit(main())
