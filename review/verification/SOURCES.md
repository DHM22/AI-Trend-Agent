# Monitoring source coverage

Measured **2026-09-20 UTC**. Only source-list entries in `02_src/monitoring_github.py` and `02_src/monitoring_rss.py` were changed, plus this requested report. Existing sources, fetch logic, filters, limits and defaults are unchanged. No verification eval was run; no verifier, other agent, schema, tool, clustering, index or eval file was edited. These changes increase collection coverage; **no verification-quality improvement is claimed**.

## Added repositories — all primary

For every repository below, `GET https://api.github.com/repos/{owner}/{repo}` with redirects disabled returned **HTTP 200**, the exact requested `full_name`, **fork=false**, **archived=false**, and **mirror_url=null**. Canonical upstream was corroborated separately by the official project page linking to that exact GitHub repository, or DSPy's package registry metadata. These are each the project's own releases, hence **primary**, not third-party reporting.

Counts are actual outputs from `clustering.py --fetch`: default **30-day** window, up to **10 fetched release records per repo**, excluding drafts/prereleases. A count is not an exhaustive release-history total.

| Added repository | Tier | Canonical upstream corroboration actually fetched | Domain relevance | Signals |
| --- | --- | --- | --- | ---: |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | primary | [Official LangGraph page](https://www.langchain.com/langgraph), HTTP 200, links to this repo | Agent orchestration; `langgraph` occurs in 11 curriculum notebooks | **1** |
| [huggingface/transformers](https://github.com/huggingface/transformers) | primary | [Official Transformers documentation](https://huggingface.co/docs/transformers/index), HTTP 200, links to this repo | BERT, inference and training; `transformers` in 36 notebooks | **3** |
| [huggingface/sentence-transformers](https://github.com/huggingface/sentence-transformers) | primary | [Official Sentence Transformers documentation](https://sbert.net/), HTTP 200, links to this repo | Embeddings/retrieval; `sentence_transformers` in 11 notebooks | **2** |
| [facebookresearch/faiss](https://github.com/facebookresearch/faiss) | primary | [Official FAISS documentation](https://faiss.ai/), HTTP 200, links to this repo | Vector indexing; `faiss` in 35 notebooks | **1** |
| [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | primary | [Published DSPy package metadata](https://pypi.org/pypi/dspy/json), HTTP 200, `info.project_urls.homepage` is this exact repository | Programmatic prompt optimization; `dspy` in one notebook | **1** |
| [evidentlyai/evidently](https://github.com/evidentlyai/evidently) | primary | [Official Evidently website](https://www.evidentlyai.com/), HTTP 200, links to this repo | RAG/LLM evaluation; `evidently` in three notebooks | **1** |

Examples establishing the curriculum relevance were read locally, without sending notebook content to a service:

- `01_data/curriculum/week_03/Demo_Langchian_Overview(Solution).ipynb` — LangGraph.
- `01_data/curriculum/week_02/HuggingFace_Intro_demo.ipynb` — Hugging Face domain.
- `01_data/curriculum/week_03/Demo_peft_lora_qwen(StudentVersion).ipynb` — Sentence Transformers keyword match.
- `01_data/curriculum/week_02/Indexing_Faiss_Basics.ipynb` — FAISS.
- `01_data/curriculum/week_02/DSPy_Facility_Support_Analyzer_Demo.ipynb` — DSPy.
- `01_data/curriculum/week_02/RAG_Evaluation_with_Evidently_sol.ipynb` — Evidently.

## Added feeds

Each retained URL was fetched with `requests.get(url, allow_redirects=False, timeout=25)` before addition. All returned **HTTP 200 with no Location redirect**, parsed as **RSS 2.0**, had **bozo=false**, and contained dated recent entries. The feed URL is directly on the publisher's domain; its channel link identifies the official blog/site below. Counts were then measured through the project's actual `feedparser`-based monitor, not inferred from XML entry counts.

| Added feed | Tier and reason | XML entries / newest entry UTC | Actual signals |
| --- | --- | --- | ---: |
| [Ollama](https://ollama.com/blog/rss.xml) | **primary**: Ollama's own official blog at `https://ollama.com/blog`; local model serving is adjacent to the curriculum's LLM/RAG domain | 58 / 2026-08-31 00:00 | **2** |
| [Qdrant](https://qdrant.tech/blog/index.xml) | **primary**: Qdrant's own official blog at `https://qdrant.tech/blog/`; vector search and retrieval are adjacent to the taught FAISS/RAG domain | 182 / 2026-09-16 07:00 | **3** |
| [PyTorch](https://pytorch.org/blog/feed/) | **primary**: PyTorch's own official site, channel link `https://pytorch.org`; model training/inference domain | 10 / 2026-09-18 00:25:32 | **10** |
| [Latent.Space](https://www.latent.space/feed) | **secondary**: third-party AI newsletter/coverage, not the upstream publisher of the projects it reports on | 20 / 2026-09-19 05:48:28 | **15**, with secondary feeds explicitly enabled |

Ollama and Qdrant are **domain expansion**, not claims that these products are explicitly taught: the local notebook scan found zero literal `ollama` and `qdrant` matches. Their actual returned posts included Ollama integration/serving updates and Qdrant multilingual RAG. Counts use the unchanged 30-day filter and first-15-entry limit. No undated or year-old feed was used to justify freshness. The existing date-conversion code was not changed; the newest-entry timestamps above are parsed from the XML in UTC.

## Actual collection output

Default command, exit **0**:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 02_src/clustering.py --fetch
```

Relevant stdout, captured during this task:

```text
  langchain-ai/langchain: 8 releases in the last 30 days
  openai/openai-python: 10 releases in the last 30 days
  chroma-core/chroma: 0 releases in the last 30 days
  fastapi/fastapi: 0 releases in the last 30 days
  langchain-ai/langgraph: 1 releases in the last 30 days
  huggingface/transformers: 3 releases in the last 30 days
  huggingface/sentence-transformers: 2 releases in the last 30 days
  facebookresearch/faiss: 1 releases in the last 30 days
  stanfordnlp/dspy: 1 releases in the last 30 days
  evidentlyai/evidently: 1 releases in the last 30 days
  langchain_blog: 14 posts in the last 30 days
  openai_blog: 15 posts in the last 30 days
  huggingface_blog: 15 posts in the last 30 days
  ollama_blog: 2 posts in the last 30 days
  qdrant_blog: 3 posts in the last 30 days
  pytorch_blog: 10 posts in the last 30 days
86 signals -> 71 clusters (10 contain more than one signal)
```

**24 additional primary signals** were actually collected: nine releases plus 15 blog posts. Every added primary source returned a nonzero count. The two existing zero-count repos were deliberately retained, as requested.

### Secondary opt-in boundary

`clustering.py:356–367` calls RSS `fetch_all()` with its existing `include_secondary=False` default. **Ordinary `clustering.py --fetch` therefore does not collect Latent.Space.** No default was changed to conceal this limitation. Its 15 signals were measured by running the same clustering CLI with the existing secondary option enabled **in memory only**, then asserting their tier is secondary:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import sys, runpy
sys.path.insert(0, '02_src')
import monitoring_rss
original = monitoring_rss.fetch_all

def with_secondary(*args, **kwargs):
    kwargs['include_secondary'] = True
    signals = original(*args, **kwargs)
    selected = [s for s in signals if s.source == 'latent_space']
    assert selected and all(s.source_tier == 'secondary' for s in selected)
    return signals

monitoring_rss.fetch_all = with_secondary
sys.argv = ['02_src/clustering.py', '--fetch']
runpy.run_path('02_src/clustering.py', run_name='__main__')
PY
```

Exit **0**; the new-source counts stayed the same and stdout additionally showed:

```text
  latent_space: 15 posts (secondary)
101 signals -> 77 clusters (12 contain more than one signal)
```

This tests opt-in collection and clustering, not persistent secondary activation. `monitoring_rss.py --secondary` is also the existing standalone CLI option for collecting these feeds. No recommendation or verification metric was measured; cluster counts do not establish event-level clustering accuracy.

## Rejected or omitted candidates

| Candidate | Observed reason not retained |
| --- | --- |
| `vibrantlabsai/ragas` | Canonical official docs linked it; GitHub metadata passed all upstream checks, but actual `fetch_releases(..., days=30)` returned **0**. Not added. This is a window/filter result, not a claim the project is inactive. |
| `https://blog.streamlit.io/rss/` | **HTTP 403**, no parsed entries. |
| `https://www.evidentlyai.com/blog/rss.xml` | **HTTP 404**, no parsed entries. |
| `https://www.roughdraft.ai/feed` | **HTTP 404**, no parsed entries. |
| `https://pytorch.org/feed.xml` | **HTTP 404**, no parsed entries. |
| `https://pytorch.org/blog/feed.xml` | **HTTP 301** to `/blog/feed/`; this redirecting URL was rejected. The separate canonical `/blog/feed/` endpoint passed HTTP 200/no-redirect/XML/freshness checks and was retained instead. |
| `https://simonwillison.net/tags/llms/atom/` | **HTTP 404**, no parsed entries. |
| `https://simonwillison.net/atom/everything/` | Valid recent Atom (HTTP 200, 30 entries, newest 2026-09-19); monitor returned 15 signals, but sampled output included unrelated wildlife content. Omitted to avoid broad mixed-topic noise. If used, it would be secondary, not primary. |

The first PyTorch `/blog/feed.xml` probe encountered an AttributeError in the probe's attempt to access a missing parser attribute; the subsequent safe inspection established HTTP 301 and no RSS entries. It was not treated as a successful feed. No failed candidate was added speculatively.

## Authentication and API impact

**GITHUB_TOKEN is SET**, checked after loading `.env` with `override=False`. Only presence was printed; no secret value was printed, recorded or changed. Authenticated metadata responses reported **X-RateLimit-Limit: 5000**, with remaining values between 4991 and 4997 during the initial probe.

The watcher now has **10 repos instead of 4**. Its existing implementation makes one release-list request per repo, so normal GitHub collection increases by **six requests per fetch**. Source-validation probes were additional one-time requests. The authenticated limit was confirmed by response headers; no GitHub rate-limit failure occurred in the fetch runs. Running elsewhere without the token would fall back to the existing unauthenticated behavior and warning.

## Offline compatibility — actual results

Neither offline implementation was modified. `TOOL_CACHE_ONLY=1` was tested with `requests.get` patched to fail if called:

```text
existing disk-cache hit: _cache=hit, return type=dict
empty temporary-cache lookup: _cache=miss, error dictionary returned
HTTP calls: 0
```

An existing cached public release response was used for the hit; no fake cache value was created. The miss used an empty temporary cache directory and `verify_release('langchain-ai/langgraph', '')`. This is a tool cache-contract check, not a verification eval or a verifier invocation.

With `OPENAI_API_KEY` removed from the replay subprocess environment and `TOOL_CACHE_ONLY=1`:

```sh
env -u OPENAI_API_KEY TOOL_CACHE_ONLY=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 02_src/demo_snapshot.py --replay
```

Actual exit **0**, stdout summary:

```text
45 signals -> 41 clusters -> 15 evaluated -> 13 recommendations
UPDATE EXISTING MATERIAL: 5  ADD NEW LESSON: 1  ADD OPTIONAL CONTENT: 1  WATCH: 6
```

`TOOL_CACHE_ONLY` is the existing tools cache contract; it does not turn the monitoring modules' explicit live `--fetch` command into an offline fetch. That behavior was preserved. Saved report files and caches were not rewritten by these checks.

## Scope and limits

An AST comparison against copies of the pre-task monitoring files confirmed every existing repository and feed entry remains unchanged. The only Python changes append the six repository names and four feed entries. `git diff --check` passed. The other engineer's existing verifier changes were not edited, staged or reverted, and no verification eval was run.

Long-term availability, completeness beyond the existing limits, event-level clustering accuracy, and downstream recommendation quality are **NOT TESTED**. These sources returned signals in the observed window; future counts will change.
