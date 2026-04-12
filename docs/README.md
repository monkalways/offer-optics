# Justin's University Application Dashboard

This directory is the published root for the GitHub Pages deployment at
**https://monkalways.github.io/offer-optics/** .

## What lives here

| File | Purpose | Edited by |
|---|---|---|
| `index.html` | Page scaffold — fonts, Tailwind config, section containers | Hand-written (rare updates) |
| `styles.css` | Custom styles layered on Tailwind (pull quote, verdict tiles, accordion, print) | Hand-written (rare updates) |
| `app.js` | Data loader + section renderers + Chart.js charts + accordion/sort interactions | Hand-written (rare updates) |
| `data.json` | All the actual data shown on the page — regenerated automatically | `tools/build_webdash.py` |
| `README.md` | This file | — |

## Viewing locally

Browsers block `fetch()` from `file://` URLs for security reasons, so you
cannot double-click `index.html` to open it. Serve the directory over HTTP
instead:

```bash
# From the repo root:
venv/Scripts/python.exe -m http.server 8000 --directory docs
```

Then open http://localhost:8000/ in any modern browser.

## Refreshing data

The data layer refreshes by re-running the Python pipeline from the repo root:

```bash
venv/Scripts/python.exe tools/fetch_sheet.py --cycle all
venv/Scripts/python.exe tools/normalize_data.py
venv/Scripts/python.exe tools/build_sqlite.py
venv/Scripts/python.exe tools/load_requirements.py
venv/Scripts/python.exe tools/analyze_program.py
venv/Scripts/python.exe tools/build_webdash.py     # updates docs/data.json
```

Then commit and push:

```bash
git add docs/data.json
git commit -m "Refresh dashboard data"
git push origin main
```

GitHub Pages picks up the change within a minute or two.

## Privacy

This is a public GitHub repo and the GitHub Pages site is publicly
accessible. All the data in `data.json` — Justin's name, school, projected
grades, extracurriculars, target programs — is visible to anyone with the
URL. The family has explicitly accepted this trade-off in exchange for the
convenience of a no-login shareable URL.
