# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# AI Trend Agent — Project Context

Capstone project for the SDA × WeCloudData Agentic AI Engineering Program.
Repo: https://github.com/RafeefAlsuhaibani/Capstone-Project, branch `feature/ai-trend-agent`.
Team lead: Dhom (Abdurahman Al-Duraywish). Four workstreams: Data/Ingestion, Agent/Tools, Platform/Security, Evaluation/QA.

## Commands

Run from the repo root (Windows/PowerShell; Python 3.10+, `pip install -r requirements.txt`, copy `.env.example` to `.env`).
`OPENAI_API_KEY` is needed only for live agent runs; `GITHUB_TOKEN` raises the GitHub rate limit.

```powershell
python 02_src/agents/test_chain.py [-v]                 # offline suite, 0 API calls (pre-merge check; plain script, no pytest)
python 02_src/tests/test_verification.py               # 19 more offline VerificationAgent tests (run both before merging)
python -c "import sys; sys.path.insert(0,'02_src/agents'); import test_chain as t; t.test_tiers()"   # one test: no filter flag, call the test_* fn
python 02_src/demo_snapshot.py --replay                 # replay frozen run, 0 API calls
python 02_src/demo_snapshot.py --capture --snapshot 01_data/experiment.json --limit 2   # live; default path OVERWRITES the committed snapshot
python 02_src/curriculum_ingest.py --curriculum 01_data/curriculum --db ./vectorstore   # (re)index
python 02_src/curriculum_ingest.py --db ./vectorstore --query "chunking" --week 2 [--type lab] [-k N]
python 02_src/monitoring_rss.py [--days N] [--secondary] [--check]
python 02_src/monitoring_github.py [--days N] [--repo owner/name]
python 02_src/clustering.py --signals 01_data/signals.json [--check|--frequencies]
python 02_src/agents/verification.py --signals 01_data/signals.json --verbose   # live agent; ~5-8 API calls/trend, use --limit/--offset
uvicorn app:app --reload                                # dashboard at :8000/ + JSON API + /docs (SNAPSHOT_PATH to change file)
python 04_eval/run_eval.py --repeats 3 --out 04_eval/results/<name>.json [--dataset ...]
python 04_eval/compare.py <baseline.json> <after.json>  # fails on different dataset hash/model
```

**Environment variables** (beyond `OPENAI_API_KEY` / `GITHUB_TOKEN`):

| var | default | why it matters |
| --- | --- | --- |
| `OPENAI_MODEL` | `gpt-4o-mini` | read by all four agents **and** `run_eval.py`. `compare.py` hard-fails when two runs disagree on it, so set it explicitly before freezing a baseline |
| `TOOL_CACHE_DIR` | `01_data/.tool_cache` (gitignored) | on-disk cache of `github_lookup` / `verify_release` responses. Only successes are cached — errors are never frozen in |
| `TOOL_CACHE_ONLY` | unset | `=1` serves tools from cache only and never touches the network; a miss comes back as `{"error": ..., "_cache": "miss"}` **data**, not an exception. This is how a live-ish run happens while the spend limit is up |
| `TOOL_CACHE_TTL` | never expires | seconds before a cache entry is stale |
| `SNAPSHOT_PATH` | `01_data/demo_snapshot.json` | which capture `app.py` serves |
| `PYTHONIOENCODING` | — | set to `utf-8` on Windows, see gotchas below |

There is no linter or build step. Ingestion is incremental (upsert): delete `vectorstore/` and re-ingest when
ingestion logic changes. See `02_src/agents/TESTING.md` for expected outputs (note: its claim that `test_chain.py`
is missing is stale — the file exists).

**Windows gotchas, both hit in practice:**
- `monitoring_rss.py` (and anything printing feed titles) dies with `UnicodeEncodeError` on the cp1252 console as
  soon as a title contains a non-ASCII character. Prefix with `PYTHONIOENCODING=utf-8`. The JSON it writes is fine;
  only the printing breaks, so a crash here does not mean the fetch failed.
- `hnrss.org` intermittently returns malformed XML. The fetcher catches it, prints
  `! <feed>: could not parse`, and reports **0 posts** — a silent-looking shortfall, not an error exit. If a
  `--secondary` capture comes back with no `hackernews_*` signals, that is this, and it succeeds on a retry.
  Always check the per-feed counts rather than the total.

## Architecture

Linear pipeline; each stage's output type is the next stage's input, all defined in `02_src/schemas.py`
(`RawSignal → TrendCluster → VerifiedTrend → CurriculumMatch → EvaluationResult → Recommendation`). Import types
from `schemas`; never copy them, and don't rename fields without telling the team. Files are in numbered dirs
(`02_src/`), so modules are run as scripts and import each other via sys.path, not as packages. `02_src/agents/`
does have an `__init__.py`, but it is a stub whose only job is that same `sys.path` insert — every module under it
repeats the insert itself so it still works when run directly.

## What this system does

Monitors GitHub releases + RSS/blog signals → clusters them → verifies they're real (not fabricated/hallucinated) →
matches verified trends against the WeCloudData curriculum via RAG → recommends one of five action tiers with
slide/cell-level citations. **The agent only recommends — a human approves.**

Tiers: `watch`, `update_existing_material`, `add_optional_content`, `add_new_lesson`, `investigate_larger_change`
(the last is deliberately unreachable — see Known Gaps).

## Repo layout

```
app.py                                 FastAPI read-only service over a captured snapshot (no agents, no API calls).
                                        Mounts ui/ at /ui LAST — a mount swallows paths beneath it, so mounting at / shadows the API
ui/theme.css                           THE design tokens (palette, dark-mode scopes, shared components). Both pages link it —
                                        one copy, so they cannot drift. Ordinal ramps validated; --tier-N-ink computed per fill
ui/trace.html                          Standalone permalink for ONE trace: trace.html?i=<index>, reads /recommendations/<i>.
                                        Since the trace also renders inline on the card, this is the shareable/full-width view,
                                        linked from the bottom of each card's trace block rather than standing in for it.
                                        Three states — searched / SEARCH FAILED / never searched. No trace in the snapshot
                                        (old capture) says so plainly instead of rendering an empty page
ui/index.html                          FRONT DOOR only — a two-way chooser ("I teach this course" / "I built this").
                                        Thin by design: one /summary fetch for the headline, and a failure there is
                                        silent because neither destination depends on it. NOT the dashboard any more
ui/simple.html                         Plain-language view for instructors/programme staff. Same data, different reader:
                                        no scores, no similarity, no tier machine names, no tool logs. Groups by what to
                                        DO (attention / optional / watch), headlines name the affected material
                                        ("Your Week 4 lab notebook may be out of date"). The failed-search state is
                                        NOT simplified away — it is the loudest thing on the card, in plain words
ui/advanced.html                       The dashboard — this is the original ui/index.html, moved here unchanged when the
                                        chooser took over "/". Everything below describes THIS file.
                                        No build step. Fetches /summary, /recommendations, /tiers same-origin.
                                        Tier + funnel scales are ORDINAL (one blue hue stepped), validated with the dataviz
                                        validator against both surfaces; in-segment label ink is computed per fill, not eyeballed.
                                        Has the Instructor Companion panel wired to POST /chat (route not built yet).
                                        Each card ENDS with its agent trace, inline in a collapsed <details> (auto-open when the
                                        curriculum search failed), built from the .trace/.tgroup/.tstep components in theme.css.
                                        The failure WARNING stays above it, un-collapsed — that must never need a click
ui2/                                   ONBOARDING PROTOTYPE, mounted at /ui2 — separate prefix, cannot shadow /ui.
                                        Every screen is simulated; the amber sticky banner on each says so, and the
                                        hand-off screen labels the dashboard as the real recorded run (green). The
                                        dashboard itself was NOT touched — labelling it there would have changed the
                                        appearance the spec froze
ui2/domains.py                         Domain config AS DATA. agentic_ai's values are IMPORTED, never copied:
                                        WATCHED_REPOS + FEEDS/SECONDARY_FEEDS + recommendation._DOMAIN_TERMS (all three
                                        import clean — the OpenAI client is built lazily inside a method). ai_engineering
                                        and cybersecurity are "not built"; cybersecurity lists NO sources on purpose.
                                        Nothing reads back: the monitoring modules and the in-domain gate are NOT rewired
                                        to use this, since that would change pipeline behaviour we cannot re-run to check.
                                        `python ui2/domains.py --write` regenerates ui2/domains.json for the pages
ui3/                                   Per-agent explainer dashboard, mounted at /ui3. One panel per agent, each with a chart
                                        from REAL snapshot data (no simulated numbers) + reveal-on-scroll animations
                                        (off under prefers-reduced-motion). Maturity/relevance are DERIVED back out of
                                        total_score using evaluation.py's bands — its JS constants mirror MATURE_FLOOR,
                                        RELEVANCE_FLOOR etc. for labelling only; update them if those move. Colours come
                                        from ui/theme.css tokens (dark mode works); source colours are dataviz-validated.
                                        Note /summary returns tier_counts as a LIST of {tier,label,count}, not a dict
demo_ui.py                             Older Streamlit dashboard over the same snapshot. Superseded by ui/advanced.html;
                                        still present, and it duplicates TIER_ORDER/TIER_LABEL instead of importing them.
                                        NOTE: streamlit is NOT in requirements.txt — this file cannot run after a clean install
01_data/curriculum/week_02..week_06/   slides (.pdf/.pptx) + labs (.ipynb), solutions + some student versions
01_data/signals.json                   30-day signal capture
01_data/signals_90.json                90-day primary-source-only (71 signals, 4-repo era)
01_data/signals_90_sec.json            90-day + secondary sources (Hacker News) (98 signals)
01_data/signals_90_new.json            90-day primary, AFTER adding langgraph+langsmith-sdk repos (92)
01_data/signals_90_sec_new.json        as above + secondary (105; short ~26 HN signals — hnrss parse failure, re-fetch)
01_data/demo_snapshot.json             frozen run used for offline/deterministic demo (COMMITTED)
02_src/schemas.py                      shared dataclasses — the data contract across all stages
02_src/curriculum_ingest.py            RAG ingestion for .pptx/.pdf/.ipynb, hybrid semantic + identifier search
02_src/monitoring_github.py            GitHub releases fetcher, filters alpha/beta/rc tags. WATCHED_REPOS = langchain,
                                        openai-python, chroma, fastapi, langgraph, langsmith-sdk (last two added for Week 5/6)
02_src/monitoring_rss.py               Blog RSS fetcher. 3 primary blog feeds; SECONDARY_FEEDS (3 Hacker News queries:
                                        langchain, AI agents, langgraph) is opt-in behind --secondary, NOT commented out
02_src/clustering.py                   Two-pass: rare-identifier match first, then title similarity (threshold 0.75)
02_src/demo_snapshot.py                Capture/replay to freeze output for demo (pipeline is measurably non-deterministic).
                                        Also captures agent TRACES: curriculum_trace_dict() / verification_trace_dict()
                                        attach a "trace" key beside to_dict() output. Keyed by id(rec) because
                                        collapse_duplicates returns the same objects. capture() sorts clusters LARGEST
                                        FIRST before slicing [offset:offset+limit] — that is why the committed snapshot
                                        shows 41 clusters but 15 evaluated. The committed snapshot predates trace
                                        capture: it has NO "trace" keys, so failed searches can't be shown until re-captured
02_src/agents/tools.py                 Tool implementations: github_lookup, search_curriculum, verify_release
02_src/agents/verification.py          Confidence is MODEL-REPORTED (clamped) — there is NO deterministic _score() or
                                        _repo_matches() (never existed in git history). Deterministic code bounds it:
                                        injection cap (<=0.1), staleness + publisher gates (-> 0.0, "contradicted"),
                                        malformed reply -> "unverified" 0.0. Sets VerifiedTrend.status (unread so far).
                                        API-failure _fallback still scores up to 0.8 from source tiers alone — the
                                        verification analogue of the curriculum silent-failure bug, not yet fixed
02_src/agents/curriculum.py            RAG search agent; has search_failed flag + curriculum_checked() tri-state
02_src/agents/evaluation.py            Deterministic _maturity_score / _relevance_score; model only writes rationale
02_src/agents/recommendation.py        Orchestrator; tier-selection gates (see Key Decisions)
02_src/agents/test_chain.py            Offline test suite — 0 API calls. Currently 118 passed, 2 skipped (the skips
                                        test a verification _score() that does not exist)
02_src/tests/test_verification.py      19 offline VerificationAgent tests (from PR #1). Plain script, run directly
04_eval/run_eval.py                    Golden-dataset harness — clustering/verification/curriculum/evaluation/
                                        recommendation layer scores
04_eval/GOLD_LABELS.md                 Labeling spec: is_genuine, confidence, stale_presented_as_new, rank,
                                        maturity, relevance, action_tier
test_signals_graded*.json (repo root, untracked)  THREE variants — see "Gold dataset: which file" below
04_eval/make_dataset.py, validate_dataset.py, compare.py   Build/validate the gold dataset; compare two eval runs
04_eval/DATASET_REQUIREMENTS.md        the spec that answers "why is this metric null" — per-gold-field, and it is
                                        explicit that recency needs a NEW output contract (e.g. VerifiedTrend.is_stale)
                                        and that labels must be event-level. Read it before relabelling anything
04_eval/results/*.json                 saved eval runs (baseline, baseline_wk5, baseline_wk5_v2, my_run, my_run_2,
                                        INVALID_offline_run). show_reqs.py (repo root) prints unmet metric
                                        requirements out of baseline_wk5.json
promptfooconfig.yaml (12 behavioral cases) is not in the tree; never run (see Known gaps)
04_eval/README.md still writes paths as evals/... — the directory is 04_eval/
```

## Key design decisions (with rationale — don't relitigate these without new evidence)

- **Identifier-first clustering before title similarity.** Title-similarity-only produced spurious cross-source
  merges. Two-pass (rare identifier match, then `threshold=0.75` title similarity, `MAX_DOC_FREQUENCY=0.08`) fixed
  it on real data. Watch out: maintainer handles (`@tiangolo`, `langchain-ai`) behave like identifiers and can
  cause false merges at MAX_DOC_FREQUENCY's ceiling — add them to STOP_IDENTIFIERS as found.
- **Deterministic scoring over model-reported confidence — in the EVALUATION agent.** The model writes rationale
  text; Python computes maturity/relevance from structured facts. Verification does NOT follow this: its
  confidence is model-reported, bounded by deterministic gates (see verification.py above). An earlier note here
  claimed a deterministic verification `_score()`; it does not exist, and the test_chain sections written for it
  report SKIPPED, not passed.
- **In-domain gate checks the signal TITLE only, not the summary.** Deliberate: vendor names in summaries (e.g.
  "OpenAI, Anthropic...") leak into `add_new_lesson` if the summary is checked too.
- **`content_type` distinguishes notebook cells from slide pages** — a broken lab cell is more urgent than an
  outdated concept slide.
- **`investigate_larger_change` tier is deliberately unreachable.** EvaluationResult carries a single match; no
  multi-module signal type exists yet. This is a documented scoping decision, not a bug.
- **Demo runs from a frozen snapshot, not live.** Same 10 signals produced tier changes on 5/10 across 3 live runs.
  Documented with a variance table rather than hidden.
- **Curriculum source slides live in Google Drive, not the repo** (redistribution concerns). Vectorstore is
  gitignored and regenerated locally from `curriculum_ingest.py`.
- **`app.py` declares no pydantic response models.** Routes return `Recommendation.to_dict()` output as plain
  dicts. A pydantic mirror of the dataclasses would be exactly the stale copy `schemas.py` forbids in its own
  header. Cost: `/docs` shows loose object schemas. Don't "fix" it by re-declaring the fields — if the frontend
  wants types, generate them from the dataclasses.
- **`app.py` is read-only and imports no agent.** Producing a snapshot is the pipeline's job; serving it is the
  API's. That split is what keeps the API working while the spend limit blocks live runs. The one exception-shaped
  thing is `GET /signals` (feeds ui3): it reads the snapshot's `source_signals` file and RE-RUNS `clustering.py`
  (pure Python, no API) because the snapshot stores only cluster counts. It returns `clusters_match_snapshot` so
  a clustering change after capture is visible instead of silently disagreeing with `clusters_total`.
- **Traces ride BESIDE `Recommendation.to_dict()`, not inside it.** `capture()` adds a `"trace"` key to each
  recommendation dict rather than adding a field to the `Recommendation` dataclass, so `schemas.py` and its team
  rule stay untouched. A snapshot without the key is valid and renders normally — every read is `.get()`-guarded.
- **Three curriculum outcomes must stay distinguishable**, and two of them look identical in the conclusion alone:
  `searched=True/search_failed=False` (looked, `reason` says what it found), `searched=True/search_failed=True`
  (tried, could not run — NOT a no-match), and `searched=False` (confidence gate skipped it; never attempted).
  The UI gives the failure a red rule and an explicit "this is NOT a finding of 'no match'". Collapsing those
  states is the original bug, not a simplification.

## Critical bug fixed — silent curriculum-search failure

`CurriculumAgent.run()` used to return `None` identically whether it searched-and-found-nothing OR the LLM call
itself failed (API error, JSON parse failure, max-steps exhaustion). This is exactly the ambiguity the tri-state
was meant to prevent, but it only covered "skipped," not "attempted and failed."

**Live proof:** an OpenAI project spend-limit error (429) caused all curriculum searches in a run to fail silently;
three trends got confidently wrong `ADD_NEW_LESSON` recommendations claiming "no existing coverage found" when no
search had actually run.

**Now also visible in the UI:** the agent-trace work surfaces this per card — a failed search gets a red rule and
an explicit contradiction of the plan text, instead of the innocuous "no curriculum match" it used to show.

**Fix:** `CurriculumTrace.search_failed` bool set on all three failure paths with a reason string;
`search_curriculum_checked()` helper returns `(match, curriculum_checked)` and is what BOTH pipelines
(`recommendation.py` main, `demo_snapshot.capture`) call; CLI prints `!! SEARCH FAILED -- this is NOT a finding of 'no match'`.
Verified offline end to end through `capture()` (test_chain section 11). **Not yet verified at scale** — needs a full re-run once API quota allows.

## Gold dataset: which file (three exist, they are NOT interchangeable)

All three are untracked at the repo root. `run_eval.py`'s `DEFAULT_DATASET` is `test_signals_graded.json`.

| file | entries | gold keys | tiers |
| --- | --- | --- | --- |
| `test_signals_graded.json` (default) | 12 | 11 — the 7 spec fields **plus** `event_id`, `is_fabricated`, `no_match_expected`, `acceptable_citations` | 10 watch, 2 optional |
| `test_signals_graded_updated.json` | 13 | 7 spec fields only | 9 watch, 3 optional, **1 update_existing_material** |
| `test_signals_graded_backup.json` | 12 | 7 spec fields only | 10 watch, 2 optional |

**The trap:** `_updated.json` is the only file with a positive `update_existing_material` case (LangChain +
LangGraph v1.0, `create_react_agent` → `create_agent`, maturity 5 / relevance 5), but it has been stripped of the
four extra fields — and `run_eval.py` reads three of them (`is_fabricated` at lines 123/126, `event_id` at 127,
`no_match_expected` at 179). Switching `--dataset` to `_updated.json` therefore **gains** a tier label and
**loses** the clustering contamination-rate and expected-cluster-count metrics, which go `null`. It is not a
strict upgrade. The merge that gets both is: take `_updated.json`'s 13 entries and restore `event_id`,
`is_fabricated`, `no_match_expected`, `acceptable_citations` onto them.

**The validator and the harness disagree about the schema.** `validate_dataset.py` requires gold keys to be
*exactly* the 7 spec fields, so it reports `gold keys must be exactly ...` for all 12 entries of the very file
`run_eval.py` defaults to. That error is expected, not a corruption signal.

**`validate_dataset.py` ignores its command-line argument** — `DATASET` is hardcoded to
`test_signals_graded.json`. Passing a path appears to work and silently validates the default file instead
(it will happily print `11/12 signals labelled.` when handed the 13-entry file). Edit the constant, or fix the
script, before trusting a validation run on a non-default dataset.

## Known gaps / honest limitations

- **The default gold dataset still has zero `add_new_lesson` and zero `update_existing_material` labels** (10×
  watch, 2× `add_optional_content`). `test_signals_graded_updated.json` now carries one
  `update_existing_material` case, but it is not the default and costs the clustering metrics to adopt — see
  "Gold dataset: which file". `add_new_lesson` is still unlabelled anywhere. Every plausible positive candidate
  found by hand failed human review — this is a documented finding, not an oversight:
  - "Announcing LangGraph v0.1" → matched cell 34, which already used the new API; the deprecated name only
    appeared in a code *comment* about the migration. Exact-identifier matching can't distinguish code from
    commentary about code.
  - "An Alien Mind" → matched an AI Ethics slide on vocabulary overlap ("alignment") but the slide teaches the
    technical alignment pipeline while the essay is a policy argument. Same word, different subject.
  - Currently hunting for a genuine positive case: `openai-python` v3.0.0 (released 2026-08-12) makes HTTPX2 the
    default HTTP client — a real breaking change. Need to check whether any Week 6 lab configures a custom HTTPX
    client/transport before this counts as a real `update_existing_material` case. **Status unknown** — the
    positive case that did land in `_updated.json` came from LangChain/LangGraph v1.0 instead, so this HTTPX2
    thread may simply be unfinished rather than resolved.
  - The LangChain/LangGraph v1.0 entry in `_updated.json` is dated `2025-10-22`, ~11 months before the current
    date, yet labelled `stale_presented_as_new: false`. Worth re-checking that label: the deprecation is real,
    but a signal that old surfacing in a 90-day capture is close to the exact case that flag exists to catch.
- **`run_eval.py`'s curriculum/evaluation/recommendation layers score `null`** until a gold entry has an expected
  citation/maturity/relevance/tier to compare against. Note that only `test_signals_graded.json` has
  `acceptable_citations` at all (4 of its 12 entries); the other two variants dropped the field entirely.
  `show_reqs.py` prints each metric's unmet `requirement` string out of `04_eval/results/baseline_wk5.json` —
  run it to see exactly what each `null` is still waiting for. Reading those strings, the nulls have **three
  distinct causes**, and only the first is a labelling problem:
  1. *Missing gold fields* — `acceptable_citations`, `no_match_expected`, `rank`, `event_id`.
  2. *Gold labels are signal-level, not event-level.* Nearly every curriculum/evaluation/recommendation metric
     wants gold keyed by event with each event mapped to its signals. Restructuring the dataset unblocks a whole
     column of metrics at once — likely the highest-leverage eval work available.
  3. *Missing output contracts, which no amount of labelling fixes.* `verification.stale_flag_rate` needs a stale
     flag that `VerifiedTrend` does not have. `curriculum.precision_at_3` needs the agent's top-3 candidates, but
     `CurriculumAgent` exposes only the one selected match. Both require a code change first.
- **Promptfoo behavioral suite (`04_eval/promptfooconfig.yaml`) has never been run** — blocked by Node version
  (need 22.22+, machine has 21.6.1). Decided to accept this gap given time constraints; test_chain.py (118 passed, 2 skipped) +
  the written config + gold-set eval numbers are the evaluation answer for now.
- **Content-Type Agent (proposed, not built):** would classify a signal as release/announcement/case_study/
  self_promotion/opinion before it reaches the tier gates. Would fix false positives from Show HN self-promotion
  and vendor case studies (found in the 90-day + secondary/HN run) passing the in-domain gate and producing
  spurious `update_existing_material`/`add_new_lesson` recs. Roadmap item, not started.
- **Instructor Companion Agent (proposed, not built):** conversational layer over recommendations + vector store.
  Roadmap item.

## Current blocker

OpenAI project spend limit was hit mid-testing (the team's OpenAI project), blocking any live agent
run (curriculum-search-failure fix verification at scale, Week 6 update-tier search, full eval re-run). Someone
with account access needs to raise it. A new API key does not help — the limit is project-level.

## Evaluation approach (three tiers)

1. Offline test suite (`test_chain.py`) — deterministic logic, no API calls, runs on every change.
2. Golden dataset (`run_eval.py` + `test_signals_graded.json`) — human-labeled signals including fabricated
   claims, run with repeats to average out LLM non-determinism.
3. Behavioral test cases (promptfoo) — targeting specific observed failures, not hypotheticals. Not yet executed.

Latest eval numbers (`test_signals_graded.json`, `--repeats 3`, pre-Week-6-positive-case):
clustering 100.00±0.00, verification 72.56±2.49, curriculum/evaluation/recommendation `null` (see Known Gaps),
composite 84.76±1.38.
