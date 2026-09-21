# AI Trend Agent

AI Trend Agent turns technology signals from official RSS feeds and GitHub
releases into evidence-backed curriculum recommendations. It searches the
course material, verifies trends, scores their curriculum impact, and produces
an action plan with citations.

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

Use Python 3.10 or newer:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
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

## Dashboard and API

One command serves both the dashboard and the JSON. Read-only, zero API calls:
it reads a snapshot captured by `demo_snapshot.py --capture`.

```powershell
uvicorn app:app --reload
```

| URL | What |
| --- | --- |
| <http://127.0.0.1:8000/> | Chooser &mdash; pick a view (`ui/index.html`) |
| <http://127.0.0.1:8000/ui/simple.html> | Plain-language view, for instructors |
| <http://127.0.0.1:8000/ui/advanced.html> | Full dashboard, for the people who built it |
| <http://127.0.0.1:8000/docs> | Interactive API docs |

There are two views of the same run, because two audiences want different
things from it. The front page asks which you are rather than guessing; both
views are bookmarkable directly, and both read the same endpoints, so they
cannot disagree.

The **plain-language view** drops the scores, similarity values, tier machine
names and tool logs, groups suggestions by what to do about them, and titles
each one by the material it affects ("Your Week 4 lab notebook may be out of
date"). It does *not* drop the failed-search warning &mdash; that is stated more
plainly there than anywhere else, because an instructor is exactly the reader
who would otherwise take it for "nothing to change".

The dashboard shows the pipeline funnel, the action-tier breakdown, and a card
per recommendation with its citation, plan, and evidence trail. It has a table
view and a light/dark toggle, and it reads the same endpoints below, so the
page and the API can never disagree.

The tier and funnel scales are one blue hue stepped light-to-dark, because both
are *ordered* scales rather than five unrelated categories. The steps and the
label colours inside each filled segment were checked against both backgrounds
rather than chosen by eye. Re-check them if you change a colour.

The **Instructor companion** panel is present but not connected: it POSTs to
`/chat`, which does not exist yet, and says so rather than pretending to answer.
Adding that route to `app.py` is all it needs.

### Agent traces

Each card ends with its own **agent trace**, showing what the agents actually
did: which sources verification checked, which curriculum searches ran with what
filters, and what came back, in the order it happened. It sits in a collapsed
section at the bottom of the card, so the dashboard still reads as conclusions
until you ask for the reasoning.

The warning for a failed search stays **above** that section, un-collapsed,
because it must not require a click — and a failed search opens its own trace
by default. `trace.html?i=<index>` remains as a full-width permalink for one
trace, linked from the bottom of each block.

A curriculum search has three outcomes, and the card distinguishes all three:

| Outcome | Shown as |
| --- | --- |
| Searched, found a match | The citation |
| Searched, found nothing | "no curriculum match" |
| **Search failed** | A red rule and "this is NOT a finding of 'no match'" |
| Never searched | "curriculum not searched" plus the reason |

The failed case is called out because confusing it with a genuine no-match once
produced confident `add_new_lesson` recommendations claiming no existing coverage
when no search had run at all.

Traces are captured by `demo_snapshot.py --capture`, so they appear only in
snapshots taken after this feature. Older snapshots, including the committed one,
render exactly as before with no trace section.

| Route | Returns |
| --- | --- |
| `GET /health` | Service status and whether the snapshot was found |
| `GET /summary` | Funnel counts and the tier breakdown |
| `GET /run` | The full captured run |
| `GET /recommendations` | Filtered list, plus `count` and `total` |
| `GET /recommendations/{index}` | One recommendation |
| `GET /tiers` | The five action tiers in display order |

`/recommendations` accepts `tier`, `week`, `content_type` (`lab` or `slides`),
`min_score`, `actionable` (drops `watch`), and `limit`. Filters combine with
AND. Each item carries an `index` into the unfiltered snapshot, so
`/recommendations/{index}` stays valid whatever the filter.

Each recommendation is exactly `Recommendation.to_dict()` from
`02_src/schemas.py`. The API does not redeclare that shape, so a schema change
reaches the response without an edit here.

Set `SNAPSHOT_PATH` to serve a different capture:

```powershell
$env:SNAPSHOT_PATH = "01_data/experiment.json"
```

## Generated files

`vectorstore/`, Python caches, virtual environments, logs, secrets, generated
run outputs, and course materials are excluded by `.gitignore`. Delete
`vectorstore/` to rebuild the local index from scratch.