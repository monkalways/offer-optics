# Workflow: Generate the Google Sheets dashboard

**Objective:** Build (or refresh) a single shareable Google Sheet that consolidates everything Justin's family needs to act on for the 2026-2027 application cycle: per-program admission stats, OOP context, year-over-year trends, decision timing, and the application requirements checklist.

**Why:** Per CLAUDE.md, deliverables go to cloud services where the user can access them directly. The Google Sheet is the single artifact the user will keep open during the cycle.

## Inputs

- `.tmp/applications.sqlite` — populated by `tools/build_sqlite.py` (with the `requirements` table populated by `tools/load_requirements.py`).
- `config/justin_profile.json` — Justin's profile, used on the Overview tab.
- `config/programs.yaml` — for program tier metadata.
- Google OAuth credentials via `tools/google_auth.py` (Sheets + Drive scopes).

## Outputs

- A Google Sheet titled "Justin — University Application Dashboard 2026" in the authorized user's Drive.
- The sheet ID persisted to `.tmp/dashboard_state.json` so subsequent runs refresh in place.
- A printed URL after each run.

## Tabs

The sheet is rebuilt on each run with these tabs (named with a numeric prefix so the order is stable):

1. **00_Overview** — Justin's profile, last refresh, top-line reach/target/safety summary, key findings/watch items.
2. **01_Per-Program Detail** — every program with rows in the applications table: tier, n_accepted, p25 / median / p75, OOP min, official competitive average (if curated), supp app required.
3. **02_Application Checklist** — the curated requirements table flattened, sorted by deadline. One row per program with deadlines, supp app type, CASPer, prereqs, fee, confidence, source URL.
4. **03_YoY Trends** — Tier-1 programs only: per-cycle accepted-average mean / min / max so we can see whether cutoffs are creeping up.
5. **04_Decision Timeline** — Tier-1 programs only: month-by-month decision histograms from the most recent complete cycle (24-25). Tells Justin when to expect news.
6. **05_Distribution** — Tier-1 programs only: binned histogram of accepted averages with Justin's projected top-6 marker for visual placement.
7. **06_Data Quality** — cycles overview, sample sizes, dataset caveats (self-selection, OOP small-sample, McMaster Cloudflare), source URLs.

## Tools

- `tools/build_dashboard.py` — the only tool; reads SQLite + YAML + profile, builds all 7 tabs, applies basic formatting (frozen header rows, bold headers).
- Reuses `tools/google_auth.py` for Sheets and Drive API services.

## Procedure

1. Ensure the upstream pipeline is fresh:
   ```bash
   python tools/fetch_sheet.py --cycle all          # if the live cycles need refreshing
   python tools/normalize_data.py
   python tools/build_sqlite.py
   python tools/load_requirements.py
   ```
2. Run the dashboard builder:
   ```bash
   python tools/build_dashboard.py
   ```
3. Open the printed URL in a browser. Spot-check the Overview tab values against `config/justin_profile.json` and `project_first_findings.md`.
4. Share the sheet with Justin and his other parent if needed (manually via Sheets UI).

## Refresh policy

- Re-run weekly while the live 2025-2026 cycles are still receiving submissions.
- Re-run after any change to `config/justin_profile.json`, `config/requirements.yaml`, or any of the saved SQL queries.
- Use `--create` to force a brand-new spreadsheet (e.g. if the existing one has been irrecoverably hand-edited or deleted).

## Known limitations

- No reach/target/safety placement column on the Overview tab until Step 4 is built (waiting on Justin's EC info).
- Embedded charts are not generated in the MVP — the Distribution tab provides the binned data, and the user can insert Sheets charts manually if desired (or we add chart generation in a follow-up pass).
- The build is destructive: each run clears and rewrites the values in every known tab. Hand-edited cells will be overwritten. Comments/notes added by the user via the Sheets UI are preserved.
