"""Fetch each program's official admissions page and save an HTML snapshot.

Reads the program list from config/programs.yaml, GETs each `official_url` with
requests, saves the response body to .tmp/requirements/{program_key}_source.html,
and writes a per-URL log to .tmp/requirements/_fetch_log.json.

This is the snapshot/provenance layer. The actual structured requirements are
hand-curated in config/requirements.yaml — see workflows/build_requirements_checklist.md.

Usage:
    python tools/fetch_requirements_pages.py                # all programs
    python tools/fetch_requirements_pages.py --tier 1       # just Tier 1
    python tools/fetch_requirements_pages.py --program mcmaster_bhsc
    python tools/fetch_requirements_pages.py --only-stale --max-age-days 7
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROGRAMS_YAML = PROJECT_ROOT / "config" / "programs.yaml"
REQ_DIR = PROJECT_ROOT / ".tmp" / "requirements"
LOG_PATH = REQ_DIR / "_fetch_log.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 OfferOptics/1.0 "
    "(personal-use; contact: monkalways@gmail.com)"
)
REQUEST_TIMEOUT = 20  # seconds
SLEEP_BETWEEN_REQUESTS = 1.0  # be polite


def load_programs() -> list[dict]:
    data = yaml.safe_load(PROGRAMS_YAML.read_text(encoding="utf-8"))
    return data.get("programs", [])


def load_existing_log() -> dict:
    if LOG_PATH.exists():
        try:
            return json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def is_stale(entry: dict | None, max_age_days: int) -> bool:
    if not entry or not entry.get("fetched_at"):
        return True
    try:
        fetched = datetime.fromisoformat(entry["fetched_at"])
    except ValueError:
        return True
    return datetime.now() - fetched > timedelta(days=max_age_days)


def fetch_one(prog: dict) -> dict:
    """Return a log entry dict; also writes the snapshot to disk on success."""
    key = prog["key"]
    url = prog.get("official_url")
    entry: dict = {
        "program_key": key,
        "url": url,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    if not url:
        entry["status"] = "no_url"
        return entry

    try:
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
            allow_redirects=True,
        )
    except requests.RequestException as e:
        entry["status"] = "error"
        entry["error"] = f"{type(e).__name__}: {e}"
        return entry

    entry["http_status"] = resp.status_code
    entry["final_url"] = resp.url
    entry["content_length"] = len(resp.content)
    entry["content_type"] = resp.headers.get("Content-Type", "")

    if resp.status_code != 200:
        entry["status"] = "http_error"
        return entry

    out_path = REQ_DIR / f"{key}_source.html"
    out_path.write_bytes(resp.content)
    entry["snapshot_path"] = str(out_path.relative_to(PROJECT_ROOT))

    # Quick heuristic: detect JS-skeleton pages so we know to fall back to WebFetch
    body = resp.text
    text_only = " ".join(body.split())
    entry["text_chars_approx"] = len(text_only)
    if "<noscript" in body.lower() and len(text_only) < 3000:
        entry["likely_js_only"] = True
    elif len(text_only) < 1500:
        entry["likely_js_only"] = True
    else:
        entry["likely_js_only"] = False

    entry["status"] = "ok"
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4],
                        help="Restrict to one tier")
    parser.add_argument("--program", help="Restrict to one program key")
    parser.add_argument("--only-stale", action="store_true",
                        help="Skip programs whose snapshot is fresh")
    parser.add_argument("--max-age-days", type=int, default=7,
                        help="Snapshot is considered stale after this many days (default 7)")
    args = parser.parse_args()

    REQ_DIR.mkdir(parents=True, exist_ok=True)
    programs = load_programs()
    if args.tier is not None:
        programs = [p for p in programs if p.get("tier") == args.tier]
    if args.program:
        programs = [p for p in programs if p.get("key") == args.program]
        if not programs:
            sys.exit(f"ERROR: program key '{args.program}' not found")

    existing_log = load_existing_log()
    if args.only_stale:
        programs = [p for p in programs if is_stale(existing_log.get(p["key"]), args.max_age_days)]

    if not programs:
        print("Nothing to fetch.")
        return 0

    print(f"Fetching {len(programs)} program page(s)...\n")
    log = dict(existing_log)
    ok = 0
    failures: list[str] = []
    js_only: list[str] = []
    for i, prog in enumerate(programs):
        entry = fetch_one(prog)
        log[prog["key"]] = entry

        status = entry.get("status", "?")
        url_display = (entry.get("url") or "")[:70]
        if status == "ok":
            ok += 1
            chars = entry.get("text_chars_approx", 0)
            js = "  [JS-only]" if entry.get("likely_js_only") else ""
            print(f"  OK   {prog['key']:35}  {chars:>6} chars{js}")
            if entry.get("likely_js_only"):
                js_only.append(prog["key"])
        elif status == "http_error":
            failures.append(prog["key"])
            print(f"  HTTP {entry.get('http_status','?')}  {prog['key']:30}  {url_display}")
        elif status == "no_url":
            print(f"  SKIP no URL  {prog['key']:30}")
        else:
            failures.append(prog["key"])
            print(f"  ERR  {prog['key']:35}  {entry.get('error','?')}")

        # Be polite between requests
        if i < len(programs) - 1:
            time.sleep(SLEEP_BETWEEN_REQUESTS)

    LOG_PATH.write_text(json.dumps(log, indent=2, sort_keys=True), encoding="utf-8")
    print()
    print(f"  Snapshots in   .tmp/requirements/")
    print(f"  Log written to .tmp/requirements/_fetch_log.json")
    print()
    print(f"Summary: {ok}/{len(programs)} ok, {len(failures)} failed, {len(js_only)} JS-only")
    if failures:
        print(f"  Failed: {', '.join(failures)}  (fall back to WebFetch for these)")
    if js_only:
        print(f"  JS-only (need WebFetch fallback): {', '.join(js_only)}")
    # Partial failures are not fatal — failed pages will be curated via WebFetch.
    # We only signal a hard error if EVERY page failed.
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
