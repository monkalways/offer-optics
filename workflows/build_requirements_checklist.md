# Workflow: Build the application requirements & deadlines checklist

**Objective:** For every program in `config/programs.yaml`, capture an authoritative, structured record of what the application package requires — deadlines, supplementary application type, CASPer/AIF/interviews, references, prerequisite courses, OOP notes, fees — sourced from each university's official admissions page.

**Why:** The Reddit dataset tells us *who got in*; this checklist tells us *what to submit so Justin doesn't miss anything*. Both feed the dashboard.

## Architecture

This workflow uses a hybrid curated-YAML approach instead of per-school HTML scrapers, because:

- Each university's site is structurally different — generic HTML parsing is unreliable.
- Several pages (Waterloo, UofT, McMaster) are JS-rendered and don't expose useful HTML to `requests`.
- Critical fields like "competitive average" are buried in prose, not structured markup.
- Curated data is higher quality and easier for the user to override.

The deterministic Python tools handle fetching/loading; the agent (Claude) does the page reading and curation.

## Inputs

- `config/programs.yaml` — list of programs with `official_url` per entry. This is the source of URLs to fetch.

## Outputs

- `.tmp/requirements/{program_key}_source.html` — raw HTML snapshot of each official page (provenance + freshness check).
- `.tmp/requirements/_fetch_log.json` — per-URL fetch status (HTTP code, content length, fetched_at, redirected_to).
- `config/requirements.yaml` — curated structured fields per program (committed, hand-edited).
- SQLite `requirements` table populated from the YAML.

## Tools

- `tools/fetch_requirements_pages.py` — fetches all official URLs, saves snapshots, writes the fetch log. Skips a program if `--only-stale` is passed and the snapshot is < 7 days old.
- `tools/load_requirements.py` — loads `config/requirements.yaml` into the SQLite `requirements` table (drops + recreates the rows). Idempotent.

## Curated YAML schema

Each entry in `config/requirements.yaml` has the following fields. **All dates are ISO `YYYY-MM-DD`. Use `null` (not omitted) when a field is genuinely unknown so we can spot gaps.**

```yaml
- program_key: mcmaster_bhsc
  source_url: https://bhsc.mcmaster.ca/future-students/admissions/
  curated_on: 2026-04-08
  curator_notes: "..."

  # Application timeline
  application_deadline_ouac:    # OUAC equal-consideration date (ON programs)
  application_deadline_supp:    # supplementary application due date
  document_deadline:            # transcripts/references/test scores due date
  decision_release_window:      # free text, e.g. "Mid-May to early June"

  # Supplementary application
  supp_app_required:            # true | false
  supp_app_type:                # "Casper", "Casper + Snapshot", "Written supp", "AIF", "Video interview", null
  supp_app_url:                 #
  supp_app_notes:               # what it actually asks for

  # Other gates
  casper_required:              # true | false
  casper_format:                # "Casper", "Casper + Snapshot + Duet", null
  interview_required:           # true | false
  interview_format:             # "KIRA video", "in-person", "MMI", null
  references_required:          # true | false
  references_count:             # int | null

  # Academic requirements
  min_average_competitive:      # float — what the program publicly cites or commonly observed
  prereq_courses:               # list of strings, e.g. ["Grade 12 English (4U)", "Grade 12 Calculus & Vectors (MCV4U)"]
  prereq_notes:                 # any min-grade caveats

  # Out-of-province / 105 considerations
  oop_eligible:                 # true | false
  oop_notes:                    # any 105/AB-specific quirks

  # Logistics
  application_fee_cad:          # int | null

  # Free-form
  notes:                        # any gotchas worth surfacing in the dashboard
```

## Procedure

1. **Verify URLs are current** — run `python tools/fetch_requirements_pages.py` and review `.tmp/requirements/_fetch_log.json`. Fix any 404s or redirects in `config/programs.yaml`.

2. **Curate one tier at a time** — start with Tier 1 (4 programs). For each program:
   - Read the snapshot HTML from `.tmp/requirements/{program}_source.html`. If the snapshot is empty / JS-only, use WebFetch to read the page directly.
   - If the official page links to a more specific admissions/requirements page, follow the link (and update `official_url` in `programs.yaml` if the new URL is more authoritative).
   - Extract the fields above. Cite the actual URL you read in `source_url`.
   - When a field is uncertain, prefer `null` over a guess. Note the gap in `curator_notes`.

3. **Load into SQLite** — run `python tools/load_requirements.py` to refresh the `requirements` table.

4. **Verify** — query for the loaded rows, compare against the source pages, fix any errors in the YAML, re-load.

5. **Iterate by tier** — once Tier 1 looks right, repeat for Tier 2, then 3, then 4.

## Refresh policy

- Re-run `tools/fetch_requirements_pages.py` weekly while the cycle is active so we spot deadline shifts or page changes.
- Re-curate any program whose snapshot has materially changed.
- Update `curated_on` whenever a YAML entry is touched.

## Known quirks (update as we learn)

- _(none yet — populate this section with site-specific gotchas as they're discovered, e.g. "Waterloo's CS page returns a JS skeleton; use the `/admissions` subpage instead")_
