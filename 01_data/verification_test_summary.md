# Verification Agent — Test Summary

Test input: `01_data/test_signals.json` (4 signals → 3 clusters)
Run command: `./run_verify.sh`

## Design: agentic decisions, deterministic score

The LLM **drives the investigation** — it reads each cluster and decides which
tool to call, whether an observation settles the question, and when to stop:

- `github_lookup(query)` — does the named repository exist and how established is it?
- `verify_release(repo, version)` — did that repo actually ship a claimed version?
  (GitHub Releases API, `/repos/{owner}/{repo}/releases[/tags/{tag}]`)

The **score is computed in Python** from facts the tools actually returned, with
hard confidence bands enforced in code. The model never emits a number, so it
cannot inflate a claim, and the score does not drift with the model.

Three states are tracked separately and never conflated:

| state | means | set by |
|---|---|---|
| `repo_exists` | a matching repository was found | `github_lookup` + exact repo match |
| `claim_verified` | the specific claimed version actually shipped | `verify_release` |
| `verified_source_count` | independent sources actually corroborated | per-source check |

Hard bands (enforced in `_enforce_bands`, no API key required):
- fewer than 2 verified independent sources → confidence ≤ 0.75
- named repository not found → confidence ≤ 0.30

## Results

| Cluster | Confidence | repo_exists | claim_verified | Verdict |
|---|---|---|---|---|
| LangGraph v1.0.0 (real, versioned) | **0.75** | yes | **yes** (release 1.0.0 confirmed) | real, version confirmed |
| NeuroForgeX 4.0 (fabricated) | **0.15** | no | no | caught — no such repository |
| vLLM (real repo, feature claim, no version) | **0.60** | yes | no | real repo, claim unverified |

`claim_verified` is what separates LangGraph (0.75) from vLLM (0.60): both are
single-source and both are real projects, but only LangGraph's specific version
claim was confirmed against the release record. Popularity (vLLM has ~91k stars)
never substitutes for that.

## Determinism

The score is identical whether the loop was driven by the model or by the
deterministic fallback, because both call the same tools and the same scorer.
Each run prints which mode gathered the evidence:

| Mode | Command | LangGraph / NeuroForgeX / vLLM |
|---|---|---|
| `agentic (LLM-driven tool loop)` | `./run_verify.sh` (key present) | 0.75 / 0.15 / 0.60 |
| `deterministic (no LLM; scripted tool loop)` | same, no `OPENAI_API_KEY` | 0.75 / 0.15 / 0.60 |

## What was fixed (and is regression-tested)

1. **No fabricated corroboration** — a source counts only when a tool actually
   checked it. The placeholder Hacker News link (`id=00000000`) is recorded as
   an unchecked source and does not raise confidence.
2. **Bands enforced in code**, not in the prompt — deterministic and testable
   without an API key.
3. **Tools are not sources** — `github_lookup` / `verify_release` output is
   tagged `kind="tool"` and excluded from the source count.
4. **Repo existence ≠ claim verification** — separate states; a real release
   check (`verify_release`) makes `claim_verified` meaningful.
5. **The real reasoning loop is surfaced** — iteration, thought, tool call, and
   observation for every step; the note is built from those facts.
6. **`results[0]` guard** — a lookup confirms a claim only if the returned repo
   is the one the signal named, not merely the top-starred hit that shares a
   token. Golden test: `test_golden_shared_token_repo_is_not_confirmation`.
   (Seen live: GitHub returned `contact4businessesp/neuroforgeX-` for
   "NeuroForgeX" and it was correctly rejected.)

## Golden test suite (T13)

`.venv/bin/python 02_src/tests/test_verification.py` — **11/11 pass** (6 golden,
5 supporting), no API key or network (the LLM client and tool dispatch are
injected). Each golden name states what it proves:

| Golden test | Proves |
|---|---|
| `test_golden_early_stop_leaves_claim_unverified` | an agent that stops early leaves `claim_verified=False` (the loop is real, not cosmetic) |
| `test_golden_shared_token_repo_rejected` | a fake repo whose top hit is a real high-star repo is rejected (`repo_exists=False`) |
| `test_golden_unopenable_source_not_counted` | a source no tool can open does not count toward `verified_source_count` |
| `test_golden_fake_version_on_real_repo_not_verified` | real repo + no matching release tag → `claim_verified=False` |
| `test_golden_missing_repo_capped_at_0_30` | a named project with no repo is capped at ≤ 0.30 |
| `test_golden_agentic_matches_deterministic` | identical evidence scores identically in both modes |

## Caching (rate-limit safety)

The loop makes up to two GitHub calls per signal (`github_lookup` +
`verify_release`). Both are wrapped by an on-disk response cache
(`01_data/.tool_cache`), keyed by tool + args, storing only successful
responses. `GITHUB_TOKEN` is read from `.env` (sourced by `run_verify.sh`).

- `./run_verify.sh` — agentic; warms the cache as it runs.
- `./run_verify.sh --cache` — sets `TOOL_CACHE_ONLY=1`; serves every GitHub
  response from disk, makes **zero network calls**, and reports any miss as data.
