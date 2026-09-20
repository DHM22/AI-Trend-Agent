# Revert attribution and isolated-field experiments

**Correction:** CR-1's 13/24 was a failed numerical guardrail, not evidence that the status field or downstream gates caused worse verification. The status field alone now passes every mandatory guardrail. Nothing has been reapplied to repository source.

## 1. What actually changed in CR-1, and what failed?

The [archived patch](implementation/cr1_reverted.patch) combined a defaulted VerifiedTrend status, a Recommendation status, downstream maturity/action gates, and saved-report consumer changes. It was not a schema-only experiment.

The unchanged harness imports the verifier and calls `VerificationAgent.run` directly (`eval/run.py:21–22,64–73`). It never invokes the evaluation or recommendation agents. The model requests contain the system prompt, signal description, tool schemas and tool responses (`02_src/agents/verification.py:229–239,252–265,278`). VerifiedTrend is constructed after the response is parsed; the added field is not a prompt or tool-schema field. The harness's final `asdict(result)` adds status to the recorded output, but the frozen checker reads confidence, notes, evidence and tools, not status (`eval/checkers.py:6–26`). Thus downstream gating was not an executed cause of this score change.

A new recorded-response experiment replayed all 102 baseline records against unchanged source, status-only source, and Evidence-only source. Under identical recorded model replies/tool results, **all 343 outbound model-request hashes matched**, and every confidence/note matched. Neither downstream agent was imported. [Comparison](isolation/replay_comparison.json), [executable probe](isolation/replay_requests.py). This is a controlled replay, not 343 additional live API requests.

The exact score changes between baseline and CR-1 are in [discordant records](isolation/cr1_discordant.json):

| Case/repeat | Baseline → CR-1 | Objective checker difference |
| --- | --- | --- |
| W01/1 | pass → fail | Expected date present, confidence 0.4; negation regex stops matching |
| W01/3 | pass → fail | Expected date present, confidence 0.4; negation regex stops matching |
| W03/3 | pass → fail | Expected tag present, confidence 0; negation regex stops matching |
| W04/1 | pass → fail | Negation present, confidence 0; expected corrective tag absent |
| W02/2 | fail → pass | Expected date present in both; negation regex begins matching |
| W03/1 | fail → pass | Expected tag present in both; negation regex begins matching |

Four losses minus two gains explains **15 → 13** exactly. For example, W01/1 changed from “does not match the actual published date of 2023-05-22” to “but the actual published date is 2023-05-22.” The checker accepts the former but not the latter (`eval/checkers.py:3,8,14`). Scores have not been relabeled. W04/1 searched `version="2.0.99"`, got no match, and reported newer versions instead of the gold correction `v2.0`; see [raw record](eval/runs/codex-cr1/W04-1.json).

**Attribution:** observed differences in model wording/search choices explain the changed scores. There is no demonstrated code-induced CR-1 regression. I did not isolate the field before the original rollback; that was a gap in the original analysis. The rollback followed the literal threshold, and should not have been presented as a causal finding or as evidence that the field itself needed verifier changes.

## 2. New isolated live tests

All new experiments use the currently retained CR-2 author payload as their common baseline, with the peer's unchanged verifier. They are not comparisons against pre-author tools. Each suite is 34 cases × 3 repeats, workers=3, pinned public sources, real model calls, unchanged cases/checkers. No private curriculum was sent. Temporary source copies were used; repository source was not modified. [Source audit](isolation/source_audit.json).

- **Status-only:** one field added to VerifiedTrend, no alias or Recommendation field, no gate/consumer changes: `status: Literal["verified", "contradicted", "unverified", "needs_clarification"] = "unverified"`. [Exact diff](isolation/status.patch).
- **Evidence-only:** four defaulted Evidence fields from the previous prototype; tools unchanged. [Exact diff](isolation/evidence.patch).
- **Metadata-only:** the previous `_with_provenance` helper applied after the existing dispatcher returns. No Evidence fields, no previous cache rewriting, direct-tool decorators, or dispatcher error-policy rewrites. All 249 observed calls had dict arguments and received metadata; maximum result JSON was 1,475 characters. This is an experimental intervention, not a production-ready replacement for the reverted patch. [Diff](isolation/metadata.patch), [observations](isolation/metadata_observations.json).
- **Control:** current repository implementation with no changes.

| Metric | Control | Status only | Evidence fields only | Metadata only |
| --- | ---: | ---: | ---: | ---: |
| Correct verdict | 88/102 | 88/102 | 85/102 | 87/102 |
| Wrong-detail | 19/24 | **21/24** | 18/24 | 18/24 |
| False refusal | 0/18 | **0/18** | 0/18 | 0/18 |
| Fabrication acceptance | 0/18 | **0/18** | 0/18 | 0/18 |
| Correct refusal | 27/27 | **27/27** | 27/27 | 27/27 |
| Half-true | 12/12 | **12/12** | 12/12 | 12/12 |
| Stale | 9/12 | 7/12 | 6/12 | 8/12 |
| Clarification | 3/9 | 3/9 | 4/9 | 4/9 |
| Harness exceptions | 0 | 0 | 0 | 0 |

Summaries: [control](isolation/control-summary.json), [status](isolation/status-summary.json), [Evidence](isolation/evidence-summary.json), [metadata](isolation/metadata-summary.json). Each changed isolated copy also passed the existing **19/19 unit tests**: [status](isolation/status-tests.txt), [Evidence](isolation/evidence-tests.txt), [metadata](isolation/metadata-tests.txt).

**The isolated status field is clean against all mandatory guardrails. There is no measured reason here to block that field for the other engineer's deterministic gate.** It remains unapplied as requested. Higher status-only scores are not a causal benefit: the replay shows the field does not affect model requests. Likewise, the stale scores must not be credited to these fields.

All new responses report `gpt-4o-mini-2024-07-18`. The unchanged verifier still supplies no explicit temperature; no sampling override was introduced. [Recorded usage/latency/cost estimates](isolation/run_costs.json). Actual billing is NOT TESTED.

## 3. Repeat spread and limits of the variance inference

Each wrong-detail repeat has 8 cases; each false-refusal repeat has 6 true cases. [Generated counts and failed case IDs](isolation/spread.json), [counting script](isolation/spread.py).

| Suite | Wrong-detail repeats 1 / 2 / 3 | Total | False-refusal repeats 1 / 2 / 3 |
| --- | --- | --- | --- |
| Original reproduced cand04 | 5/8 · 5/8 · 5/8 | 15/24 | 0/6 · 0/6 · 0/6 |
| CR-1 combined candidate | 4/8 · 6/8 · 3/8 | 13/24 | 0/6 · 0/6 · 0/6 |
| Retained CR-2 | 6/8 · 6/8 · 6/8 | 18/24 | 0/6 · 0/6 · 0/6 |
| Original full provenance candidate | 6/8 · 5/8 · 7/8 | 18/24 | 0/6 · 1/6 · 0/6 |
| New unchanged CR-2 control | 6/8 · 8/8 · 5/8 | 19/24 | 0/6 · 0/6 · 0/6 |
| New status only | 5/8 · 8/8 · 8/8 | 21/24 | 0/6 · 0/6 · 0/6 |
| New Evidence fields only | 6/8 · 5/8 · 7/8 | 18/24 | 0/6 · 0/6 · 0/6 |
| New metadata only | 7/8 · 6/8 · 5/8 | 18/24 | 0/6 · 0/6 · 0/6 |

**13/24 has not been established as outside normal run variation.** The original baseline's three equal totals did not mean identical case outcomes: repeat 1 failed W03 while repeats 2/3 failed W02, in addition to W07/W08. The new unchanged control varies from 5/8 to 8/8 within one suite and differs from the previous same-source CR-2 total. Three repeats per condition are not enough to characterize a reliable tail distribution or establish a small causal effect. Different source conditions must not be pooled as though they were repeated controls. No statistical-significance claim is made.

## 4. Provenance revert: what is and is not explained

The original [full patch](implementation/provenance_reverted.patch) was not metadata-only: it combined Evidence fields, response metadata, cache-hit normalization/persistence, tool decorators, and dispatcher changes. No component-only live test preceded its rollback.

The single false refusal was [T03 repeat 2](eval/runs/codex-provenance/T03-2.json):

1. `verify_release(encode/httpx, 0.24.1)` successfully returned the exact release, URL, date and author `lovelydinosaur`.
2. The model requested an additional `github_lookup("lovelydinosaur")`, although the claim did not assert publisher identity.
3. Pinned transport lacked that query and returned `Pinned public snapshot unavailable for this exact request` (`eval/run.py:37`). This was not a demonstrated real GitHub outage.
4. The model assigned 0.4 because the publisher was “unverified due to a network error,” rejecting a true release claim.

This establishes the **proximate failure: an unnecessary publisher check plus a replay fixture miss governed acceptance despite sufficient release evidence**. It does not establish which patch component, if any, caused the model to choose that check. No exception or payload truncation explained it in the recorded candidate.

The new Evidence-only experiment is clean and request-equivalent under controlled replay. Metadata-only is also clean across 18 true-case runs; T03 passed all three repeats (confidence 0.85, 1.0, 0.85), with no publisher-account lookup. Unlike schema fields, tool metadata is actually model-visible (`verification.py:262–265`), so it can change subsequent requests. The clean isolation run does not prove it can never contribute to a refusal, nor does it identify the previous cache/decorator changes as the cause.

**The old 1/18 versus 0/18 difference is not established as a causal regression or as outside run variation.** It was a genuine observed false refusal under the frozen checker and a mandatory threshold failure. Cache-only/decorator/dispatcher components and their interactions have NOT BEEN TESTED separately in live ablations. The complete provenance prototype has not been re-run in this follow-up. Neither schema nor tool metadata has been reapplied.

## Commands and experiment integrity

`prepare.py` builds temporary source copies. A second preparation produced byte-identical Python files to the measured copies: [check](isolation/reproduction_check.json). Original measured paths are in [manifest](isolation/paths.json); those temporary directories are not durable artifacts. Saved patches document the exact interventions.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/isolation/prepare.py
# Substitute a printed temporary root and a NEW run ID for each mode:
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/isolation/launch.py <temporary-root> --run-id <new-id> --repeats 3 --workers 3 --offline-sources
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/analyze.py --run-id <new-id>
# Measured control:
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/run.py --run-id codex-isolate-control --repeats 3 --workers 3 --offline-sources
# Identical-response probe, run for repository root and each schema-only copy:
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/isolation/replay_requests.py <source-root> codex-repro-cand04
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/isolation/spread.py
```

An initial isolated-runner launch failed before model calls because spawned workers interpreted rewritten argv as a source path. The wrapper was corrected to inherit the isolated root through an environment variable, then the complete status suite ran successfully. No agent/checker was edited to fix the runner. All four completed suites have 102 records and zero harness exceptions.

No implementation commit or reapplication was made in this follow-up. Dashboard/replay compatibility was NOT re-tested here: these are isolated verification-core ablations, not proposed retained consumer changes. Production source, existing gold cases/checkers and the curriculum index remain untouched.
