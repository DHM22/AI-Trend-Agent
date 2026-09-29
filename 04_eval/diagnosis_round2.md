# Verifier error diagnosis, round 2 — v2 dev split

**Scope:** diagnosis only, no file edits (this report excepted). **Dev split
only — the test split was never loaded or run.**

## Method & validity

`/tmp/v2_dev_evidence_diagnostic.json` (Codex) is **valid**: its
`sha256 = b58c995f…` equals `run_eval.read_dataset(v2, "dev")`'s digest for the
**current** dataset (i.e. after round-1's pydantic relabel + fastapi-owner fix —
its rows show `pydantic v3.0.0` as fabricated and `fastapi/fastapi` as the
owner). It is the deterministic, cache-only reproduction of the verifier, and it
reproduces the stated **0.7188 accuracy = 23/32 correct, 9 wrong**.

Two caveats:

- **Clustering is non-deterministic in ordering.** My own independent
  deterministic cache-only rerun got **10** wrong (0.6875), differing from Codex
  only on items whose confidence is set by *which cluster they land in*
  (`langgraph v1.0.0`, both `openai-python` releases, `langchain==2.0.0`, the
  FastAPI-Django item…). That instability is itself evidence for cause **(b)**
  below. I anchor the numbers on Codex's file because it matches the sha and the
  0.72 you cited; treat the exact wrong-set as ±1 item.
- **`TOOL_CACHE_ONLY=1`** means several `github_lookup` calls come back as cache
  misses (unchecked), which contributes to — but is not the whole of — the 0.40
  band on the genuine secondary items.

Accuracy uses `(confidence >= 0.5) == is_genuine` (run_eval's rule).

---

## 1. The 9 wrong items, each with its single main cause

| # | title | gold | conf | main cause | fix side |
|---|-------|------|------|-----------|----------|
| 1 | `openai/openai-python: v9.0.0` | fabricated | **0.75** | **(b) mixed cluster** | clustering / dataset |
| 2 | `langchain-ai/langgraph: v1.0.0` | genuine | **0.20** | **(b) mixed cluster** | clustering / dataset |
| 3 | `The LangChain blog: mandatory migration to QuantumChains` | fabricated | **0.60** | **(d) missing check** | verifier |
| 4 | `LangGraph 1.0 is out — durable execution…` (HN) | genuine | 0.40 | **(c) band too low** | verifier |
| 5 | `Chroma 0.6 changes the collection.add signature` (tech_blog) | genuine | 0.40 | **(c) band too low** | verifier |
| 6 | `Someone benchmarked FAISS vs Chroma HNSW…` (reddit) | genuine | 0.40 | **(c) band too low** | verifier |
| 7 | `Hugging Face ships Transformers v5.2…` (HN) | genuine | 0.40 | **(c) band too low** | verifier |
| 8 | `Dev blog: migrating our agents to create_agent` (tech_blog) | genuine | 0.40 | **(c) band too low** | verifier |
| 9 | `Mastodon thread: LangSmith SDK 0.14 adds OTel export` (tweet) | genuine | 0.40 | **(c) band too low** | verifier |

**No item is cause (a) invented/404 URL or cause (e) gold-wrong.** Round-1's
dataset fixes cleared those; every remaining error is a verifier or clustering
limitation, not a dataset defect. That is the headline: **the dataset is now
sound; the ~0.72 ceiling is the verifier.**

### Detail on the non-obvious cases

- **#1 `openai-python v9.0.0` — mixed cluster (b).** It was clustered with the
  **genuine** `openai-python: v3.11.0` (same repo identifier). The cluster's
  trend inherits v3.11.0's *confirmed* release record → "claim CONFIRMED via
  release record" → 0.75, and that 0.75 is applied to the fabricated v9.0.0 too.
  Its own `verify_release('…','v9.0.0')` was a cache miss and never got to fire.
  Un-merged, v9.0.0 scores ≤0.45 (repo exists, release unconfirmed) → correct.
- **#2 `langgraph v1.0.0` — mixed cluster (b), the mirror image.** It was
  clustered with the **fabricated** `langchain==2.0.0`. Its *own*
  `verify_release('langgraph','v1.0.0')` **CONFIRMED** the 1.0.0 release — but
  the fabricated sibling's unconfirmable `langchain==2.0.0` sets the cluster's
  `release_missing` flag, and `release_missing` (0.20) is checked *before* the
  confirmed-release band, so it **poisons** the genuine item down to 0.20.
  (Secondary verifier note: `release_missing` from one signal overriding a
  *confirmed* release on another signal in the same cluster is itself dubious
  logic — but the root enabler is the bad merge.) Un-merged, langgraph v1.0.0
  scores 0.75 → correct.
- **#3 QuantumChains — missing check (d), NOT a band-lowering fix.** The
  fabricated first-party post gets a **0.60 "first-party provisional prior"**
  even though its cited page 404s ("source page not found") and nothing is
  verified. It is tempting to call this "band too high (c)", but **the 0.60
  first-party prior is load-bearing for three genuine items** (`MCP in
  LangChain` 0.60, `Introducing structured outputs` 0.60, `OpenAI structured
  outputs GA` 0.60 — all correct). Simply lowering the prior fixes 1 and breaks
  3 (net −2). The clean fix is the **missing check**: withhold the first-party
  prior when the cited first-party URL does not resolve. QuantumChains 404s;
  the three genuine posts resolve — so this check fixes #3 with zero collateral.
- **#4–#9 — band too low (c).** Six genuine *secondary* posts (HN, reddit,
  tweet/Mastodon, dev blogs) about **real, confirmable** events (LangGraph 1.0,
  Chroma 0.6, Transformers v5.2, LangSmith 0.14, `create_agent`). None names an
  `owner/repo` the tool can look up; the verifier's fallback token lookups
  (`github_lookup('v5.2')`, `'collection.add'`, `'create_agent'`, `'faiss'`,
  `'langsmith'`) either miss the cache or can't identify the repo, so
  `verified_source_count = 0` and the band floors at **0.40** ("no
  claim-matching source document confirmed") — below the 0.5 threshold. The
  underlying releases are confirmable (e.g. `verify_release` returns
  release_found=True for `transformers v5.2.0`, and the langgraph 1.0.0 release
  is confirmed on the primary item), but the verifier never links the prose post
  to them.

---

## 2. Cause tally and "fix this cause alone" accuracy

Base: **23/32 = 0.719**. Causes are disjoint across the 9 items, so estimates
add cleanly.

| cause | items | fix type | acc if fixed alone |
|-------|-------|----------|--------------------|
| **(c) band too low** — genuine secondary, real event, unconfirmed | 6 (#4–9) | **verifier** | 23+6 = **29/32 = 0.906** |
| **(b) mixed cluster** — genuine & fabricated share a cluster | 2 (#1,#2) | clustering / dataset | 23+2 = **25/32 = 0.781** |
| **(d) missing check** — first-party prior not gated on URL resolving | 1 (#3) | **verifier** | 23+1 = **24/32 = 0.750** |
| (a) invented/404 URL in gold | 0 | — | — |
| (e) gold label wrong | 0 | — | — |

Combined: (c)+(b) → **31/32 = 0.969**; all three → **32/32 = 1.00**.

**Caveat on (c):** the 0.906 assumes the verifier can actually *confirm* those 6
real events (via repo extraction from the summary/URL and cross-signal event
linking) rather than blindly raising the floor — a blind raise would also lift
the many fabricated *secondary* items over 0.5 and create new false positives.
The confidently-recoverable subset (LangGraph 1.0, Transformers v5.2, LangSmith
0.14, Chroma 0.6 — all confirmable) is ~4; `create_agent` and the FAISS
benchmark are harder, so the realistic (c) gain is **+4 to +6 → 0.84–0.91.**

---

## 3. Verifier vs dataset, and the biggest single fix

- **Verifier changes:** cause (c) — the six genuine-secondary false negatives —
  and cause (d) — the first-party-URL gate. **7 of 9 errors are verifier-side.**
- **Clustering / dataset changes:** cause (b) — two mixed clusters. This is a
  *clustering* (pipeline) fix (don't merge different release tags of the same
  repo; don't let `langgraph` and `langchain` co-cluster), or a *dataset*
  mitigation (don't place a genuine and a fabricated release of the same repo,
  or same-family versions, in the set). It is **not** a verifier fix and **not**
  a gold-label fix.

**Biggest single gain: cause (c)** — teaching the verifier to confirm genuine
*secondary* posts about real events (repo extraction from the summary + linking
a prose signal to a confirmable release). It alone lifts accuracy to **~0.91**,
and it is the **only** single fix that can clear 0.90: (b)+(d) together reach
just 0.813, because the six 0.40-floored genuine-secondary items are the actual
wall between 0.72 and 0.90.

> Why it's stuck at 0.72 in one line: after round-1 cleaned the dataset, the
> verifier's only positive instrument is a matched **GitHub release record**, so
> genuine events that arrive as *prose from a secondary source* (no owner/repo
> to look up) park at the 0.40 floor — and two same-repo mixed clusters flip a
> genuine and a fabricated item on top of that.
