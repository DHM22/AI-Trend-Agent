# Verifier error diagnosis — v2 dev split

**Scope:** diagnosis only, no fixes. Read-only. The **test split was never
loaded or run** — every number below is the **dev split only**.

## Method & important caveats (read first)

`04_eval/results/v2_dev_baseline.json` stores **only aggregate metrics** — it
has no per-item confidences, so it alone cannot tell you *which* items were
missed. It also records `dataset.sha256 = 55153ad7…` with `item_count: 32`
(dev), whereas the current `test_signals_graded_v2.json` hashes to `b2e4129…`
(45 items, 32 dev / 13 test). The dataset was regenerated after that baseline
run; the dev **count** (32) still matches, and `read_dataset(..., "dev")`
reproduces the recorded dev digest `55153ad7…`, so the dev items line up.

To recover per-item confidences I reran the eval's own path
(`run_eval.read_dataset(..., "dev")` → `cluster_signals` → `VerificationAgent`)
with **no OpenAI key** (the documented deterministic tool loop, *same scorer*)
and **`TOOL_CACHE_ONLY=1`** (network-free, replays the cache the baseline left).
This gives **18/32 correct = 0.5625 accuracy**, close to the baseline's
recorded `classification_accuracy = 0.59375` (19/32). The small gap is the
model-driven baseline vs the deterministic loop picking tool calls, plus one
release-record check discussed below.

**Two caveats that matter for interpretation:**

1. The baseline was **model-driven** (`gpt-4o-mini-2024-07-18`); this
   reproduction is the **deterministic** verifier. The scorer is identical
   (`verification._score`), so confidence *bands* transfer, but the exact
   per-item tool calls can differ by ~1 item.
2. Under `TOOL_CACHE_ONLY=1`, `verify_release` for a few specific tags is a
   **cache miss → error**, which the scorer treats as *unchecked* (never
   "missing"). This directly affects the two GitHub false-positives (§2b): with
   the release check available they would very likely drop to the "release not
   found" band and be classified correctly. The **false-negatives (§2a) are
   not** cache artifacts — they are structural band floors.

`classification_accuracy` uses `(confidence >= 0.5) == is_genuine`
(`run_eval.verification_metrics`), so "wrong side of 0.5" = genuine scored
`< 0.5`, or fabricated scored `>= 0.5`.

---

## 1. Every dev item the verifier got wrong (14 items)

| # | gold | verif conf | title | source / tier | has_url | repo in title | event |
|---|------|-----------|-------|---------------|---------|---------------|-------|
| 1 | **fabricated** | **0.75** | `openai/openai-python: v9.0.0` | github / primary | yes | yes | evt-fab-openai9 |
| 2 | **fabricated** | **0.75** | `langchain-ai/langchain: langchain==2.0.0` | github / primary | yes | yes | evt-fab-lc2 |
| 3 | genuine | 0.15 | `tiangolo/fastapi: 0.120.0` | github / primary | yes | yes | evt-fastapi-120 |
| 4 | genuine | 0.20 | `pydantic/pydantic: v3.0.0` | github / primary | yes | yes | evt-pydantic-3 |
| 5 | genuine | 0.20 | `LangGraph 1.0 is out — durable execution and a frozen API` | hackernews / secondary | yes | no | evt-langgraph-1 |
| 6 | genuine | 0.40 | `Chroma 0.6 changes the collection.add signature` | tech_blog / secondary | yes | no | evt-chroma-06 |
| 7 | genuine | 0.40 | `Someone benchmarked FAISS vs Chroma HNSW after the 0.6 release` | reddit / secondary | yes | no | evt-faiss-bench |
| 8 | genuine | 0.40 | `Mastodon thread: LangSmith SDK 0.14 adds OTel export` | tweet / secondary | yes | no | evt-langsmith-14 |
| 9 | genuine | 0.45 | `MCP in LangChain: stateless protocol and elicitation` | langchain_blog / primary | yes | no | evt-mcp-namespace |
| 10 | genuine | 0.45 | `Introducing structured outputs for the Responses API` | openai_blog / primary | yes | no | evt-structured-out |
| 11 | genuine | 0.45 | `Pydantic v3 lands with a strict-by-default core` | tech_blog / secondary | yes | no | evt-pydantic-3 |
| 12 | genuine | 0.45 | `Hugging Face ships Transformers v5.2 with tensor-parallel loading` | hackernews / secondary | yes | no | evt-transformers-52 |
| 13 | genuine | 0.45 | `OpenAI makes structured outputs GA on the Responses API` | tech_blog / secondary | yes | no | evt-structured-out |
| 14 | genuine | 0.45 | `Dev blog: migrating our agents to create_agent` | tech_blog / secondary | yes | no | evt-create-agent |

**Shape of the errors:** 12 of 14 are **genuine items scored below 0.5**
(false negatives); only 2 are fabricated scored at/above 0.5 (false positives).
The verifier's failure mode on v2 is overwhelmingly **under-confidence on real
events**, not gullibility.

---

## 2. Patterns — what the wrong items share

The scorer's confidence bands (`verification._base_confidence`) are the whole
story. Nothing reaches ≥ 0.5 without **either** a confirmed release record
(`claim_verified`) **or** ≥ 2 independently verified sources:

```
repo_missing        -> 0.15      release_missing            -> 0.20
repo_exists only    -> 0.45      unresolved (nothing found) -> 0.40
n==1 verified src   -> 0.60      n==1 + claim_verified      -> 0.75
n>=2                -> 0.80      n>=2 + claim_verified      -> 0.95
```

### 2a. False negatives — genuine "prose" signals with nothing checkable (10 of the 12)

Items 5–14 are **blog / forum / social posts about real events** whose title
names **no repository or release tag** (`repo in title = no`). The verifier has
nothing to look up, so it lands on the **unresolved (0.40)** or
**repo-exists-only (0.45)** floor — both below 0.5. This hits every secondary
tier (hackernews, reddit, tweet, tech_blog) *and* two first-party blogs
(langchain_blog #9, openai_blog #10) equally. The `_has_first_party` note
fires but does **not** raise the score.

> This is exactly what breaking the source-tier shortcut exposed. The v2 set
> deliberately added genuine secondary/forum signals; the verifier cannot lift
> any of them over 0.5 because its only real confirmation instrument is a
> GitHub **release record**, which a prose post never provides.

Same-event corroboration does **not** rescue them: e.g. `evt-structured-out`
(#10, #13) and `evt-pydantic-3` (#4, #11) each have two signals, but clustering
did not merge them into one ≥2-source cluster, so each stays single-source and
capped at the single-source ceiling (0.75) — and, lacking a release record,
never even climbs to it.

### 2b. False negatives — genuine GitHub releases the repo/release check couldn't confirm (2 of the 12)

- **#3 `tiangolo/fastapi: 0.120.0` → 0.15 (repo_missing).** `_repo_matches`
  fails: `github_lookup('tiangolo/fastapi')` returns
  `tiangolo/uvicorn-gunicorn-fastapi-docker`, `…full-stack-fastapi-couchbase`,
  … but **not** an exact `tiangolo/fastapi`. The repo was renamed to the
  `fastapi/fastapi` org, so the **stale owner in the title** makes a real
  project look nonexistent → the 0.15 "fabricated" floor.
- **#4 `pydantic/pydantic: v3.0.0` → 0.20 (release_missing).** The repo *does*
  match, but `verify_release('pydantic/pydantic','v3.0.0')` (cache **hit**)
  returned `release_found=False` — there is **no v3.0.0 release record**. See
  §3, this is also a gold-label red flag.

### 2c. False positives — fabricated tags on real, watched repos (both of them)

- **#1 `openai/openai-python: v9.0.0`** and **#2 `langchain==2.0.0`** both →
  **0.75**. The named repo is real and matches (`openai/openai-python`,
  `langchain-ai/langchain` both appear in results), so `repo_exists=True`. The
  fabricated **tag** is what's false — but `verify_release` for these tags was
  a **cache miss (error)** in this offline replay, and an errored release check
  is scored as *unchecked*, **not** `release_missing`. So the fake release
  evades the 0.20 penalty and rides the repo-existence / verbatim-tag path to
  the single-source ceiling 0.75.

  **Contrast:** other fabricated GitHub items whose release check *did* return
  not-found were caught correctly — `chroma-core/chroma: 1.0.0-agi` → 0.20,
  `openai/whisper: v4.0.0…` → 0.20. And genuine watched-repo releases hit the
  same 0.75 (`langgraph v1.0.0`, `openai-python v3.11.0`,
  `transformers v5.2.0`). **The verifier therefore assigns the identical 0.75
  to a real and a fake `openai-python` release** — repo existence + tag string,
  not release truth, drives the score whenever the release-record check is
  unavailable. This is the one place the two false-positives are contingent on
  the cache-miss caveat; with the release check live they would most likely
  land at 0.20.

### Field-distribution of the 14 wrong items

`has_url` is **True for all 14** (v2 removed the empty-url tell), so it carries
no signal. `tier` splits 6 primary / 8 secondary and `repo in title` 4 yes / 10
no — i.e. **no single input field predicts the errors**, mirroring the
leakage-check design. The predictor is internal: *did a release-record or
≥2-source check succeed*, which correlates with neither tier nor source.

---

## 3. Gold-label sanity check (genuine items only)

Assessed against project canon (CLAUDE.md references) and tool evidence. The
project is set in a fictional 2026, so "real" here means *internally
consistent / confirmable*, and anything unconfirmable is flagged.

**Consistent / plausible (no concern):**

- `langchain-ai/langgraph: v1.0.0` and `LangGraph 1.0 is out …` — canon
  (LangGraph 1.0, `create_agent`).
- `openai/openai-python: v3.11.0` — canon (3.x line; v3.10/v3.14 referenced).
- `MCP in LangChain …` — canon (`evt-mcp-namespace` exists in the original set).
- `Introducing/OpenAI makes structured outputs … Responses API` — plausible.
- `Mastodon thread: LangSmith SDK 0.14 adds OTel export` — canon
  (`langsmith-sdk v0.14.0`).
- `Dev blog: migrating … to create_agent` — canon.
- `Chroma 0.6 …` / `… FAISS vs Chroma HNSW after the 0.6 release` — plausible
  (Chroma 0.4/0.5/0.6 lineage).

**⚠ FLAGGED — labelled genuine but I cannot confirm the release exists:**

1. **`pydantic/pydantic: v3.0.0` (item #4) and `Pydantic v3 lands …` (item #11)
   — event `evt-pydantic-3`.** `verify_release` (cache hit) says **no v3.0.0
   release record exists**, and Pydantic was on the v2.x line as of the Jan-2026
   knowledge cutoff. Both signals for this event are labelled genuine; the
   release is **unverified and quite possibly fabricated**. This is the single
   strongest label concern — a fabricated-looking event is labelled genuine, so
   the verifier's 0.20 here may actually be *correct* and the **gold** wrong.
2. **`huggingface/transformers: v5.2.0` (item, scored 0.75 OK) and `Hugging
   Face ships Transformers v5.2 …` (item #12) — event `evt-transformers-52`.**
   Transformers was on the v4.x line at cutoff; a v5.2 is a large,
   **unconfirmable** jump. Not caught by the run (the github item rode
   repo-existence to 0.75), but the "genuine" label rests on an unverifiable
   release. Flag for review.
3. **`tiangolo/fastapi: 0.120.0` (item #3) — identifier, not the event.** FastAPI
   0.120.0 is a plausible real release, but the **owner `tiangolo/` is stale**
   (project moved to the `fastapi/fastapi` org). The label may be fine while the
   *title identifier* is wrong, which is itself what drove the 0.15 score. Under
   `TOOL_CACHE_ONLY`, `fastapi/fastapi 0.120.0` was a cache miss, so I could not
   positively confirm the release in this run either.

**Fabricated side (spot-check):** all 17 fabricated dev items read as clearly
fabricated (QuantumChains, AGI/self-healing claims, "no code", per-thought
billing, etc.); no mislabels spotted there.

---

## 4. Root-cause summary

1. **The verifier's only positive evidence is a GitHub release record (or ≥2
   corroborating checked sources).** Any genuine event that surfaces as a
   blog/forum/social post with no repo-or-tag in its title structurally caps at
   0.40–0.45 and is classed fabricated. v2's genuine secondary/blog items — the
   ones added to break the source-tier shortcut — are precisely this case, and
   account for 10 of the 14 errors. *(structural, not a cache artifact.)*

2. **Repo existence ≠ release truth.** A fabricated tag on a real, watched repo
   scores the same 0.75 as a real release from that repo whenever the specific
   release-record check does not return "not found" (here, because it errored
   under cache-only). Fabricated releases whose check *did* return not-found
   were caught (0.20). *(the 2 false-positives are contingent on this caveat.)*

3. **Stale/misattributed identifiers penalize genuine events.** A real project
   under a renamed owner (`tiangolo/fastapi`) fails `_repo_matches` and hits the
   0.15 "repo missing" floor.

4. **At least one gold label is likely wrong the other way** (`pydantic v3.0.0`,
   and `transformers v5.2` is suspect), so a slice of the measured "error rate"
   may be the dataset, not the verifier — separate the two before tuning.

*No files were edited. Confidences are the deterministic-verifier reproduction
described in "Method"; treat the two §2c false-positives as caveat-dependent.*
