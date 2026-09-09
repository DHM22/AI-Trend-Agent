# AI Trend Agent

AI Trend Agent combines course curriculum knowledge with fresh signals from
official RSS feeds and GitHub releases. It indexes curriculum content in a
local Chroma vector store so the future agent workflow can retrieve relevant,
citable course material and turn verified trends into recommendations.

## Project structure

```text
01_data/
   curriculum/week_02/     Course material for week 2
   curriculum/week_03/     Course material for week 3
   signals.json             Saved monitoring signals
02_src/
   agents/                  Agent stubs and future tool definitions
   schemas.py               Shared dataclass contracts
   curriculum_ingest.py     Extract and index PDF/PPTX content
   monitoring_github.py     Fetch GitHub releases
   monitoring_rss.py        Fetch official RSS posts
   clustering.py            Group signals into trend clusters
   pipeline.py              End-to-end pipeline stub
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
`OPENAI_API_KEY` when the agent workflow is implemented. Never commit `.env`.

Course slides are excluded from Git because of their size and redistribution
restrictions. Place downloaded PDF, PPTX, or notebook files in the matching
`01_data/curriculum/week_NN/` directory.

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

`vectorstore/`, Python caches, virtual environments, logs, secrets, and course
materials are excluded by `.gitignore`. Delete `vectorstore/` to rebuild the
local index from scratch.