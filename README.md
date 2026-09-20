# AI Trend Agent

AI Trend Agent turns technology signals from official RSS feeds and GitHub
releases into evidence-backed curriculum recommendations. It searches the
course material, verifies trends, scores their curriculum impact, and produces
an action plan with citations.

## Curriculum Trend Monitor dashboard

A read-only, server-rendered FastAPI dashboard for a saved curriculum report.
It needs **Python 3.11+**, no API keys, no database, and no JavaScript build step.

### Install and run

From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

On Windows, activate with `.venv\Scripts\Activate.ps1` instead.
Open **http://127.0.0.1:8000**. Stop the server with Ctrl+C.

The included `data/report.json` is an unchanged copy of the repository's
`01_data/demo_snapshot.json`: 13 recommendations captured on 13 September 2026,
including seven null curriculum matches and two low-confidence items. It is a
saved report, not a live pipeline run.

### Use another report

```bash
REPORT_PATH=/absolute/path/to/another-report.json uvicorn app.main:app --reload
```

PowerShell:

```powershell
$env:REPORT_PATH = "C:\reports\another-report.json"
uvicorn app.main:app --reload
```

`REPORT_PATH` defaults to `data/report.json`. Relative paths resolve from the
repository root. The file is read and validated on each page/API request;
refresh the page after replacing it. Environment variables are read directly;
the dashboard does not load `.env` or call the agents.

### Routes and behavior

- `GET /`: report dashboard, sorted by score and then confidence, highest first.
- `GET /api/report`: the validated report JSON, preserving source order and
  additional snapshot metadata. Missing optional fields have null/default values.
- `GET /health`: `{"status": "ok"}`; checks server liveness independently of the report.

Click an action card or **All** to filter; search matches trend titles and combines
with the selected action. **Details** reveals evidence, plans, and course content.
The footer announces the visible count. Without JavaScript, all recommendations
and details remain readable. Missing values display neutral placeholders;
missing action counts are derived from the recommendations. Present `tier_counts`
values are displayed as supplied, without rewriting the report.

Missing/unreadable files or invalid JSON/schema return a friendly page and HTTP
503; `/api/report` returns a friendly JSON error with the same status. Confidence
and similarity must be finite numbers from 0 to 1, and scores from 0 to 5.
Timestamps display in UTC; timestamps without a timezone are assumed to be UTC.
Evidence links use `url`, falling back to `source`, and permit only HTTP(S).
All report text is escaped. Inter is loaded from Google Fonts when available,
with a system-font fallback for offline presentations.

### Dashboard files

```text
app/
  main.py
  models.py
  templates/
    base.html
    index.html
  static/
    style.css
    app.js
data/report.json
requirements.txt            Minimal dashboard dependencies, pinned
requirements-pipeline.txt   Optional original pipeline dependencies, pinned
```

The original pipeline remains available below. To run its scripts, additionally
install `python -m pip install -r requirements-pipeline.txt`.

### Deploy the demo to Netlify

The Netlify deployment is a **static snapshot** generated from the same validated
report and Jinja templates. Python runs at build time; FastAPI is not started on
Netlify. Search, action filters, and expandable details still work in the browser.

1. In Netlify, choose **Add new project → Import an existing project → GitHub**.
2. Select `DHM22/AI-Trend-Agent` and branch **`feat/curriculum-report-ui`**.
3. Leave the base directory empty. The committed `netlify.toml` supplies:
   - Build command: `python -m app.export_static`
   - Publish directory: `dist`
   - Python version: `3.11`
4. Deploy. No OpenAI key, GitHub token, or other application secret is needed.

Netlify installs `requirements.txt` before building. `REPORT_PATH` is optional;
it defaults to the committed `data/report.json`. A custom path must exist in the
build checkout. Update the report on this branch and push to trigger a fresh
deployment. Refreshing the website alone does not rebuild a static snapshot.
Invalid or missing reports fail the build so they do not replace a good deploy.

The published `/api/report` serves the validated JSON produced at build time,
and `/health` serves `{"status": "ok"}` as a static response (not a Python-process
health check). Only six generated files in `dist/` are published: the page, CSS,
JavaScript, report JSON, health JSON, and Netlify redirects. Report content,
including its curriculum excerpts, is visible to site visitors.

Preview the static files locally:

```bash
python -m app.export_static
python -m http.server 8080 --directory dist
```

Open http://localhost:8080. Python's simple preview server does not implement
Netlify rewrites, so use `/api/report.json` and `/health.json` during this preview.
The FastAPI development command above continues to provide the original live
file-reading routes.

References: [Netlify Python builds](https://docs.netlify.com/build/configure-builds/manage-dependencies/#python)
and [Netlify rewrites](https://docs.netlify.com/manage/routing/redirects/rewrites-proxies/).

## Project structure

```text
01_data/
   curriculum/week_02/     Course material for week 2
   curriculum/week_03/     Course material for week 3
   signals.json             Saved monitoring signals
02_src/
   agents/                  Verification, curriculum, evaluation, and recommendation agents
   schemas.py               Shared dataclass contracts
   curriculum_ingest.py     Extract and index PDF/PPTX content
   monitoring_github.py     Fetch GitHub releases
   monitoring_rss.py        Fetch official RSS posts
   clustering.py            Group signals into trend clusters
   demo_snapshot.py         Capture or replay a recorded run
03_assets/
   diagrams/                Project diagrams
   screenshots/             Project screenshots
vectorstore/                Local generated Chroma database
```

## Setup

For the original pipeline, use the same Python 3.11+ environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-pipeline.txt
Copy-Item .env.example .env
```

Set `GITHUB_TOKEN` in `.env` for the higher GitHub API rate limit and
`OPENAI_API_KEY` for live agent runs. Never commit `.env`.

Course slides are excluded from Git because of their size and redistribution
restrictions. Place downloaded PDF, PPTX, or notebook files in the matching
`01_data/curriculum/week_NN/` directory.

## Quickstart without an API key

Replay the committed run. This makes zero API calls:

```powershell
python 02_src/demo_snapshot.py --replay
```

For the full command list, observed outputs, offline checks, and troubleshooting,
see [02_src/agents/TESTING.md](02_src/agents/TESTING.md).

## Run the existing scripts

### Curriculum ingestion

```powershell
python 02_src/curriculum_ingest.py --curriculum 01_data/curriculum --db ./vectorstore
python 02_src/curriculum_ingest.py --db ./vectorstore --query "LangChain agents"
python 02_src/curriculum_ingest.py --db ./vectorstore --query "chunking" --week 2
```

The script also accepts `--week` to restrict a query and `-k` to set the
number of results.

### RSS monitoring

```powershell
python 02_src/monitoring_rss.py
python 02_src/monitoring_rss.py --days 60
python 02_src/monitoring_rss.py --secondary
python 02_src/monitoring_rss.py --check
```

### GitHub monitoring

```powershell
python 02_src/monitoring_github.py
python 02_src/monitoring_github.py --days 60
python 02_src/monitoring_github.py --repo langchain-ai/langchain
```

Repeat `--repo` to override the watched repository list.

### Clustering

```powershell
python 02_src/clustering.py --signals 01_data/signals.json
python 02_src/clustering.py --fetch --save 01_data/signals.json
python 02_src/clustering.py --signals 01_data/signals.json --check
```

Clustering also accepts `--threshold`, `--strip-prefix`, `--no-identifiers`,
`--max-freq`, `--frequencies`, `--min-shared`, and `--all`.

## Generated files

`vectorstore/`, Python caches, virtual environments, logs, secrets, generated
run outputs, and course materials are excluded by `.gitignore`. Delete
`vectorstore/` to rebuild the local index from scratch.
