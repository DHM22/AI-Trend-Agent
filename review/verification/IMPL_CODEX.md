# Data/tools/schema implementation report — in progress

Read `IMPL_CLAUDE.md` and all four requested prior-review documents. The missing-report blocker is resolved. The other engineer's modified `verification.py` is preserved unchanged. No eval case/checker or sampling/model setting has been changed.

## Reproduced baseline

Fresh run: `codex-repro-cand04`, 34 cases × 3 repeats, unchanged harness with `--offline-sources`. Evidence: [summary](implementation/repro_summary.json), [log](implementation/repro.log), [raw records](eval/runs/codex-repro-cand04/). Unit tests independently passed 19/19.

| Metric | Shipped cand04 | Reproduced baseline | CR-1 attempt (reverted) |
| --- | ---: | ---: | ---: |
| False refusal | 0/18 | 0/18 | 0/18 |
| Fabrication acceptance | 0/18 | 0/18 | 0/18 |
| Correct refusal | 27/27 | 27/27 | 27/27 |
| Half-true | 12/12 | 12/12 | 12/12 |
| Wrong-detail | 15/24 | 15/24 | **13/24** |
| Correct verdict | 82/102 | 81/102 | 82/102 |
| Clarification | 6/9 | 5/9 | 4/9 |
| Stale | 4/12 | 4/12 | 8/12 |

Materiality decision before implementation: every hard guardrail and stale result matched exactly. One fewer clarification pass accounts for the one fewer overall pass; treated as non-material run variance, not a changed baseline. The response model was `gpt-4o-mini-2024-07-18` on all 343 reproduced model responses.

**Sampling discrepancy:** neither model-call site in `02_src/agents/verification.py:236–239,278` supplies temperature. The unchanged harness at `review/verification/eval/run.py:58` forwards keyword arguments without adding it. [AST call-site record](implementation/sampling_call_sites.json). Therefore the report's assertion of temperature 0 cannot be confirmed from this checkout. No setting was changed, injected or inferred. Explicit temperature-zero behavior is **NOT TESTED**.

## CR-1 — reverted, not shipped

The attempted minimal field was `status: VerificationStatus = "unverified"`, with `VerificationStatus = Literal["verified", "contradicted", "unverified", "needs_clarification"]`. Confidence remained unchanged and the field was appended to dataclasses for positional compatibility. A full per-claim structure was deliberately deferred: a scalar status is enough for the peer's upcoming deterministic gate; an unused list that the current parser cannot populate would over-build.

Attempted consumer changes: `02_src/schemas.py` (VerifiedTrend and Recommendation), `02_src/agents/evaluation.py` (maturity and CLI gate), `02_src/agents/recommendation.py` (tier, propagation, CLI gate), `02_src/demo_snapshot.py` (capture/load/replay), `app/models.py` (defaulted typed status), `app/main.py` (load/status/action propagation). Missing status became unverified; non-verified rows were read as watch in memory, without rewriting saved reports. No changes were made to `verification.py`, curriculum files or the index.

Deterministic checks improved: confidence 1.0 previously produced maturity 5 / update-existing-material without a status gate; attempted contradicted/unverified/needs_clarification statuses produced maturity 1 / watch, even with supplied maturity 5. [Before](implementation/cr1_prior_gate.json), [after](implementation/cr1_status_checks.json).

The required full evaluation nevertheless produced **13/24 wrong-detail**, below the absolute required **15/24**. Per the user's no-exceptions rule, all six source files were restored to their recorded pre-task hashes. No source change was committed. Patch retained for handoff: [cr1_reverted.patch](implementation/cr1_reverted.patch). [Eval summary](implementation/cr1_summary.json), [log](implementation/cr1_eval.log), [unit results](implementation/cr1_unit_tests.txt), [post-revert unit results](implementation/cr1_revert_unit_tests.txt).

The confidence-based evaluator does not inspect the added status, and the verifier's model input/tool payloads were unchanged by CR-1. The observed metric changes are not established causal effects of CR-1. In particular, **no stale improvement is claimed**. The hard numerical rule still requires rollback; this was not selectively rerun until it passed.

**Current status field: absent. Current consumers touched by a retained change: none.** The main task remains unblocked only by a future successfully validated status change. The peer will also need to explicitly produce verified status on accepted cases; a default-unverified field must never infer that from a float.

## Compatibility actually run

Baseline: [baseline_compatibility.json](implementation/baseline_compatibility.json). Attempted CR-1: [cr1_compatibility.json](implementation/cr1_compatibility.json).

- Both `01_data/demo_snapshot.json` and `data/report.json` load 13 recommendations.
- ASGI application lifespan started with FastAPI TestClient; `/health`, `/`, `/api/report` each returned HTTP 200 for both report paths. Server-rendered HTML was 48,188 bytes at baseline and 48,052 with CR-1. Browser JavaScript execution is **NOT TESTED**.
- With `OPENAI_API_KEY` removed and `TOOL_CACHE_ONLY=1`, `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 02_src/demo_snapshot.py --replay` exited 0. Baseline summary: `UPDATE EXISTING MATERIAL: 5  ADD NEW LESSON: 1  ADD OPTIONAL CONTENT: 1  WATCH: 6`. CR-1 summary: `WATCH: 13`, because all legacy rows lacked verified status. Saved files were not rewritten.

## Commands

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 02_src/tests/test_verification.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/run.py --run-id codex-repro-cand04 --repeats 3 --workers 3 --offline-sources
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/analyze.py --run-id codex-repro-cand04
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/run.py --run-id codex-cr1 --repeats 3 --workers 3 --offline-sources
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/analyze.py --run-id codex-cr1
```

## CR-2 — kept

`02_src/agents/tools.py` now returns `author` in matched_release and every recent-release entry. It extracts only a string login from the API's author object. Missing/null authors remain an empty string. Legacy disk-cache records lacking this field are normalized to an empty string in memory; cache keys, cache-only behavior and stored records remain compatible. No author is invented and no network refresh is forced in offline mode.

The existing public snapshots already contain author.login. [Extracted fixtures](eval/fixtures/release_authors.json) identify HTTPX `lovelydinosaur` and Pydantic `samuelcolvin`, and point to those snapshots; no existing snapshot, case or checker was changed. [Payload/cache checks](implementation/cr2_payload_checks.json) verify matched and recent authors, legacy cache hits, cache-only misses without network, and dispatcher error dictionaries.

Fresh run `codex-cr2`, 102 results: [summary](implementation/cr2_summary.json), [log](implementation/cr2_eval.log). Compared with reproduced baseline: wrong-detail **15/24 → 18/24**, correct **81/102 → 84/102**; false refusal **0/18**, fabrication **0/18**, correct refusal **27/27**, half-true **12/12**, stale **4/12**, clarification **5/9** unchanged. All required metrics pass. Ancillary URL provenance was 66/102 versus 67/102, and the unchanged decisive-evidence checker reports 27/102 versus 31/102; these are reported, not hidden, and no provenance improvement is claimed from CR-2.

Wrong-publisher improved **0/6 → 2/6** under the frozen checker. All six raw outputs name the actual author, but four say “but the actual author ...” without a word matching the checker's negation regex. They remain failures in every metric; no checker was adjusted. This demonstrates the added source field's use without inventing credit for unrelated run variation.

[Unit tests](implementation/cr2_unit_tests.txt): **19/19 passed**. [Compatibility](implementation/cr2_compatibility.json): both saved reports load 13 recommendations; ASGI startup, health, dashboard HTML and API all return 200; dashboard HTML is 48,188 bytes; no-key cache-only replay exits 0 with the original 5/1/1/6 tier counts. Status remains absent because CR-1 was reverted.

Commands:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/run.py --run-id codex-cr2 --repeats 3 --workers 3 --offline-sources
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/analyze.py --run-id codex-cr2
```

## Remaining work

Provenance metadata, source-coverage decision and final comparison are pending. No sources added yet. No change to the recency gate is implemented or proposed in clustering. Private curriculum is isolated from live evaluation as in the existing harness.
