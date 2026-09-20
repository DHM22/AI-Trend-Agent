# Data/tools/schema implementation report

**Corrected attribution:** the original CR-1 revert was **not evidence of a code regression**. [Isolated experiments](ISOLATION_FINDINGS.md) showed identical request hashes and a clean schema-only live run. At the user’s direction, the exact tested VerifiedTrend field is now shipped and available for the other engineer’s deterministic staleness gate. No gating or provenance changes were reapplied.

**Current retained source: CR-2 release-author payload plus the single defaulted VerifiedTrend.status field. Consumer gates and provenance remain absent. Local verification passes. The completed one-worker three-repeat live rerun has 327 model responses, zero API failures, and passes all mandatory guardrails: correct verdict 86/102, wrong-detail 20/24, false refusal 0/18. The earlier infrastructure-affected runs remain documented separately below.**

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

## Original bundled CR-1 — historical rollback; field-only change now shipped

The attempted minimal field was `status: VerificationStatus = "unverified"`, with `VerificationStatus = Literal["verified", "contradicted", "unverified", "needs_clarification"]`. Confidence remained unchanged and the field was appended to dataclasses for positional compatibility. A full per-claim structure was deliberately deferred: a scalar status is enough for the peer's upcoming deterministic gate; an unused list that the current parser cannot populate would over-build.

Attempted consumer changes: `02_src/schemas.py` (VerifiedTrend and Recommendation), `02_src/agents/evaluation.py` (maturity and CLI gate), `02_src/agents/recommendation.py` (tier, propagation, CLI gate), `02_src/demo_snapshot.py` (capture/load/replay), `app/models.py` (defaulted typed status), `app/main.py` (load/status/action propagation). Missing status became unverified; non-verified rows were read as watch in memory, without rewriting saved reports. No changes were made to `verification.py`, curriculum files or the index.

Deterministic checks improved: confidence 1.0 previously produced maturity 5 / update-existing-material without a status gate; attempted contradicted/unverified/needs_clarification statuses produced maturity 1 / watch, even with supplied maturity 5. [Before](implementation/cr1_prior_gate.json), [after](implementation/cr1_status_checks.json).

The required full evaluation nevertheless produced **13/24 wrong-detail**, below the absolute required **15/24**. Per the user's no-exceptions rule, all six source files were restored to their recorded pre-task hashes. No source change was committed. Patch retained for handoff: [cr1_reverted.patch](implementation/cr1_reverted.patch). [Eval summary](implementation/cr1_summary.json), [log](implementation/cr1_eval.log), [unit results](implementation/cr1_unit_tests.txt), [post-revert unit results](implementation/cr1_revert_unit_tests.txt).

The confidence-based evaluator does not inspect the added status, and the verifier's model input/tool payloads were unchanged by CR-1. The observed metric changes are not established causal effects of CR-1. In particular, **no stale improvement is claimed**. The hard numerical rule still requires rollback; this was not selectively rerun until it passed.

**Current status field: absent. Current consumers touched by a retained change: none.** The main task remains blocked until a future status change passes the required validation. The peer will also need to explicitly produce verified status on accepted cases; a default-unverified field must never infer that from a float.

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

Fresh run `codex-cr2`, 102 results at **`--repeats 3 --workers 3`** (the reproduced baseline also used three workers): [summary](implementation/cr2_summary.json), [log](implementation/cr2_eval.log). Compared with reproduced baseline: wrong-detail **15/24 → 18/24**, correct **81/102 → 84/102**; false refusal **0/18**, fabrication **0/18**, correct refusal **27/27**, half-true **12/12**, stale **4/12**, clarification **5/9** unchanged. **Attribution correction:** the wrong-detail 15→18 and correct-verdict 81→84 deltas are checker-lexical/run-to-run variance, not a measured improvement caused by exposing `author.login`. Passing the required thresholds does not establish causality. CR-2 supplies a previously omitted source field; these runs do not establish a verification-quality benefit. Ancillary URL provenance was 66/102 versus 67/102, and the unchanged decisive-evidence checker reports 27/102 versus 31/102; these are reported, not hidden, and no provenance improvement is claimed from CR-2.

Wrong-publisher scores were **0/6 → 2/6** under the frozen lexical checker; this is not a demonstrated causal quality improvement. All six raw outputs name the actual author, but four say “but the actual author ...” without a word matching the checker's negation regex. They remain failures in every metric; no checker was adjusted. The outputs show that author information was available and mentioned. They do not establish that the field caused the aggregate metric deltas; the negation-regex sensitivity makes those counts wording-dependent. No verification-quality improvement is claimed from CR-2, consistent with the separate source-coverage report in [SOURCES.md](SOURCES.md).

[Unit tests](implementation/cr2_unit_tests.txt): **19/19 passed**. [Compatibility](implementation/cr2_compatibility.json): both saved reports load 13 recommendations; ASGI startup, health, dashboard HTML and API all return 200; dashboard HTML is 48,188 bytes; no-key cache-only replay exits 0 with the original 5/1/1/6 tier counts. Status remains absent because CR-1 was reverted.

Commands:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/run.py --run-id codex-cr2 --repeats 3 --workers 3 --offline-sources
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/analyze.py --run-id codex-cr2
```

## Priority 3 — provenance prototype reverted

The prototype added `_provenance` to each tool result, containing `source_id`, `canonical_url`, `retrieved_at`, `tool_result_id` and `origin`. It retained original observation metadata across disk-cache hits and used a SHA-256-based identifier. Errors and legacy caches had null retrieval time rather than invented timestamps. Evidence gained optional/defaulted counterparts without breaking the old constructor. Direct tools and dispatch errors returned dictionaries. This was data/schema work only; no verifier parser, prompt, confidence or sampling change was made.

Local [payload checks](implementation/provenance_payload_checks.json) passed: cold/warm result identity equal, real canonical release URL, timestamp present for fresh observations, unknown legacy time preserved, zero network calls on cache-only hit/miss, error dictionaries with IDs, old Evidence constructor compatible. All **248/248** results in the live eval carried metadata; max tool JSON was **1,475 characters**, below the verifier's 4,000-character truncation. [Observation counts](implementation/provenance_observations.json). In replay, these timestamps represent tool observation time, not live upstream revalidation.

Nevertheless, the 102-run candidate violated the mandatory false-refusal constraint: **1/18**, versus zero required. Wrong-detail was 18/24 and half-true 12/12, but clarification also fell to 1/9 and correct verdict to 80/102. [Summary](implementation/provenance_summary.json), [full log](implementation/provenance_eval.log). The candidate was reverted to committed CR-2; no metadata or Evidence schema extension remains in source. [Reverted patch](implementation/provenance_reverted.patch). Unit tests were **19/19**, and [compatibility checks](implementation/provenance_compatibility.json) passed before rollback; these did not override the failed guardrail.

### Exact incident and scope boundary

[T03 repeat 2](eval/runs/codex-provenance/T03-2.json) received a successful matched HTTPX release with tag `0.24.1`, author `lovelydinosaur` and publication timestamp. It then searched repositories for `lovelydinosaur`. The frozen replay transport returned **“Pinned public snapshot unavailable for this exact request”**. This is a fixture miss, **not evidence of an actual GitHub outage**. The model's final confidence was 0.4 and its note:

> The release 0.24.1 was found, but the publisher (lovelydinosaur) is unverified due to a network error while checking the specific account.

The claim asserted only publication of the release, not a publisher identity. The verifier already instructs against inventing extra parts (`02_src/agents/verification.py:91–103,143–146`), but `_parse` still takes the model's confidence directly (`299–303`). There were four successful model responses and no harness exception. Successful release evidence was available; the extra lookup should not have governed acceptance. No claim is made that metadata alone causally caused this stochastic behavior.

**Stopping at the ownership boundary:** enforcing that only actually asserted subclaims affect acceptance requires the verifier owner's work. The precise needed behavior is: identify asserted fields from claim text; for a plain publication claim with a matching primary release record, a failed lookup about an unclaimed publisher must not downgrade that claim; required publisher assertions must still compare the claimed login to the returned author. This belongs in `verification.py`'s decision/gating path, not clustering or a tool that lacks claim context. CR-1 must also be successfully coordinated/validated before that gate can set typed status. No such gate was implemented here, and no extra fixture was added to mask the unnecessary publisher check.

The shipped prompt at `verification.py:113–115,125–127` still says the tool has no author. That is now outdated after CR-2. The other engineer's requested follow-up can replace the publisher instruction with: “When a publisher is asserted, compare the claimed account to matched_release.author. If author is empty, the publisher is unverified; if it differs, state the actual author. Do not check publisher identity for a claim that does not assert one.” This is documented only; **the prompt was not changed**. A deterministic asserted-field gate, not this text alone, is the proposed protection against the observed extra-claim refusal.

## Priority 4 — no source additions retained or attempted

No new source/provider/feed was added. The retained change exposes a field already present in an existing **primary** source: the project's GitHub release object. Its evidence and authority are the captured exact release records referenced by the author fixtures. It fixes the measured missing-publisher-field problem without expanding the provider set.

`02_src/monitoring_github.py:50–55` remains four repos; `02_src/monitoring_rss.py:42–53` remains three primary blogs and no secondary feeds. The frozen harness directly constructs TrendCluster (`review/verification/eval/run.py:64`) and bypasses both monitors. Therefore adding monitored repos/feeds cannot be credited with fixing its observed wrong-detail or stale failures. Live collection coverage and added-feed impact are **NOT TESTED**. No demonstrated collection omission justified a new source under the user's “fix something measurable” rule. The provenance incident involved unnecessary account checking, not a missing release record; more sources are not presented as its fix.

## Earlier reproduced-baseline versus CR-2 metrics (before schema-only delivery)

“Final” below means the **kept CR-2 revision**, measured in `codex-cr2`. The failed provenance candidate is shown separately above and was restored byte-for-byte to that tested source state; it is not relabeled as a passing run. Four complete 102-run suites were executed: reproduction, CR-1, CR-2 and provenance. The baseline/CR-2 comparison below used **three workers** and is a historical score comparison, not evidence that the author payload improved verification quality.

| Metric | Reproduced cand04 | Retained CR-2 | Decision |
| --- | ---: | ---: | --- |
| False refusal | 0/18 | 0/18 | Required zero retained |
| Fabrication acceptance | 0/18 | 0/18 | Required zero retained |
| Correct refusal | 27/27 | 27/27 | Retained |
| Half-true | 12/12 (100%) | 12/12 (100%) | No regression |
| Wrong-detail | 15/24 (62.5%) | 18/24 (75.0%) | Checker-lexical/run variance; no causal improvement claimed |
| Correct verdict | 81/102 (79.4%) | 84/102 (82.4%) | Checker-lexical/run variance; no causal improvement claimed |
| Clarification | 5/9 (55.6%) | 5/9 (55.6%) | Unchanged; supplied cand04 had 6/9 |
| Stale | 4/12 (33.3%) | 4/12 (33.3%) | Unchanged; no stale improvement claimed |
| Wrong-publisher | 0/6 | 2/6 | Wording-sensitive score difference; no causal improvement established |
| URL provenance | 67/102 | 66/102 | Ancillary measure lower by one; reported, not claimed improved |
| Decisive evidence + correctness | 31/102 | 27/102 | Ancillary measure lower; checker hard-excludes publisher support at `eval/checkers.py:21–22` |

Token/latency observations: reproduced baseline 343 model responses, 642,573 tokens, estimated $0.074643, mean 4.44s/p95 6.97s; retained CR-2 317 model responses, 588,899 tokens, estimated $0.064478, mean 3.91s/p95 7.19s. Actual billing is **NOT TESTED**, and stochastic response-count/latency differences are not a demonstrated causal optimization. The entire four-suite exercise used 1,342 model responses and an estimated $0.291387. All were the same returned model `gpt-4o-mini-2024-07-18`; no model/sampling setting was changed.

## Earlier CR-2 compatibility and audit

After rollback, the 19 unit tests passed again: [final log](implementation/final_unit_tests.txt). A real Uvicorn process was started on localhost with the API key removed; `/health`, `/`, `/api/report` returned **200**. HTML was **48,198 bytes** and the JSON endpoint **17,239 bytes**. The server was explicitly terminated after the checks; its log confirms application shutdown completed. [HTTP results](implementation/final_dashboard_http.json), [server log](implementation/final_dashboard_server.log). Both report files also passed the per-stage load/render tests above, and the kept CR-2 offline replay exited 0 without a key. Browser JavaScript/visual layout remains **NOT TESTED**; actual server-side rendering and startup were tested.

[Final scope audit](implementation/final_scope_audit.json): of 64 initial source/config/eval fingerprints, **only `02_src/agents/tools.py` differs**. The peer's pre-existing `verification.py` changes have exactly the same hash as at task start. All 13 index files checked against the previous snapshot remain unchanged. Saved JSON reports, sampling settings, eval cases/checkers and prohibited source files were not modified. Private curriculum was not sent to the live model; the unchanged public-only harness isolation remained in place.

Separate commits: `1b49d7c` records CR-1 rollback; `53cc983` retains CR-2 author payload. A final documentation commit records provenance rollback and final evidence. The unapplied patches remain available for coordinated follow-up; they are not shipped source changes.

## Remaining NOT TESTED / not implemented

- **Typed status is now shipped on VerifiedTrend only.** Consumer changes remain reverted. Original confidence-only gating remains; setting status from the deterministic gate belongs to the other engineer.
- **Per-claim provenance schema/metadata is not shipped.** Prototype coverage is recorded, but the failed false-refusal run prevented keeping it. Claim-to-tool reference validation was never implemented in the protected verifier.
- Explicit temperature 0 cannot be verified from the existing call sites; no unapproved sampling override was introduced.
- No new monitoring sources, registry adapter or live source-coverage benchmark; no causal stale-detection gain.
- No changed gold labels, regexes or native-status scorer. The frozen checker remains conservative and can miss correct wording; it was not adjusted to make a candidate pass.
- No live private-curriculum pipeline execution, external tracing service, browser JavaScript automation or actual account-billing validation.

Additional commands run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/run.py --run-id codex-provenance --repeats 3 --workers 3 --offline-sources
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/analyze.py --run-id codex-provenance
```


## Current delivery — exact schema-only status field

`02_src/schemas.py:102` now contains exactly:

```python
status: Literal["verified", "contradicted", "unverified", "needs_clarification"] = "unverified"
```

Confidence is retained. The file is byte-identical to the earlier status-only isolation condition. No Recommendation field, consumer normalization, evaluation/recommendation gate, model setting, verifier prompt/parser, or provenance field was added. Only schemas.py changes in this delivery; the earlier CR-2 tools change remains. [Scope audit](implementation/status_shipped_scope.json).

**The original CR-1 rollback was not evidence of a code regression.** The harness never executes downstream gates, and identical-response replay produced identical 343 model-request hashes with and without the schema field. The observed 13/24 was a threshold failure affected by wording-sensitive checks and run variation, not a demonstrated field effect. The field is now available for the peer to set from their deterministic staleness gate. No improvement in verification behavior is attributed to adding it.

### Local checks and legacy status semantics

[19/19 unit tests pass](implementation/status_shipped_tests.txt). [Executable compatibility check](implementation/check_status_compatibility.py) and [actual results](implementation/status_shipped_compatibility.json):

- `01_data/demo_snapshot.json`: 13 recommendations load; all 13 lack status. Constructing VerifiedTrend from those legacy rows without status yields **unverified for all 13**, including when confidence is high.
- `data/report.json`: same 13/13 missing-status default result.
- A real Uvicorn process was started separately for each report, with OPENAI_API_KEY removed. For each, `/health`, `/`, `/api/report` returned **200**. Dashboard HTML was **48,198 bytes**, report JSON **17,239 bytes**. Both servers were terminated after the checks.
- Offline `demo_snapshot.py --replay`, with OPENAI_API_KEY removed and TOOL_CACHE_ONLY=1, exited **0** and printed: `45 signals -> 41 clusters -> 15 evaluated -> 13 recommendations`; `UPDATE EXISTING MATERIAL: 5  ADD NEW LESSON: 1  ADD OPTIONAL CONTENT: 1  WATCH: 6`.

**Boundary of the missing-status guarantee:** saved reports contain Recommendation rows, not serialized VerifiedTrend. The unchanged dashboard/replay readers retain an absent status field; they do not materialize an `unverified` property, and do not synthesize `verified`. The VerifiedTrend constructor defaults missing status to unverified. Normalizing the saved Recommendation/API contracts themselves would require consumer changes outside the explicitly requested schema-only scope. Those changes were not made. Browser JavaScript is NOT TESTED; actual server startup and rendered HTML over HTTP were tested. Saved report files were not rewritten.

### Earlier requested evaluation: API quota blocked (resolved by subsequent live rerun)

The exact requested full eval command ran all 102 cases, then the unchanged analyzer ran:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 02_src/tests/test_verification.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/run.py --run-id codex-status-shipped --repeats 3 --workers 3 --offline-sources
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/analyze.py --run-id codex-status-shipped
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/implementation/check_status_compatibility.py
```

**All 102 cases hit HTTP 429 `project_spend_limit_exceeded`; there were zero successful model responses.** They exercised the existing source-tier fallback, not model verification. All returned status=unverified. [Failure counts](implementation/status_shipped_api_block.json), [analyzer output](implementation/status_shipped_summary.json). The analyzer reports no harness exception because the agent catches the API failure itself.

| Metric | New quota-blocked fallback run — invalid quality baseline | Earlier exact status-only live isolation |
| --- | ---: | ---: |
| Correct verdict | 36/102 | 88/102 |
| Wrong-detail | 0/24 | 21/24 |
| False refusal | 18/18 | 0/18 |
| Fabrication acceptance | 0/18 | 0/18 |
| Correct refusal | 27/27 | 27/27 |
| Half-true | 0/12 | 12/12 |
| Clarification | 9/9 | 3/9 |
| Stale | 0/12 | 7/12 |
| Successful model responses | 0 | 333 |

The prior isolation numbers are explicitly historical, not represented as a successful new rerun. No quality regression or improvement is inferred from the quota-blocked results. At that point fresh live-model validation was **NOT TESTED successfully: API quota unavailable**. This blocker is now resolved in the subsequent live run below after the user updated the local key. The assistant did not change credentials, billing limits, model or sampling settings. The schema-only change is retained as explicitly directed.

After the user updated the key, the following **new run ID** was used so the harness did not skip the 102 saved fallback records:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/run.py --run-id codex-status-shipped-live --repeats 3 --workers 3 --offline-sources
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/analyze.py --run-id codex-status-shipped-live
```


### Three-worker live rerun after user updated key — two rate-limit fallbacks

The single public probe `codex-status-keycheck/T01-1` passed with two successful model responses. Then `codex-status-shipped-live` completed **102 cases / 3 repeats**, with **342 successful model responses**, **two API-failure notes** and zero harness exceptions. Q03/3 hit a token-per-minute rate limit after five responses; E02/3 hit it before any response. These were `rate_limit_exceeded`, not the earlier project spend-limit error. [Full summary](implementation/status_shipped_live_summary.json), [audit](implementation/status_shipped_live_audit.json), [raw results](eval/runs/codex-status-shipped-live/). The prior quota-fallback run is not included in these metrics.

| Metric | Fresh shipped-field live result |
| --- | ---: |
| Correct verdict | **85/102 (83.3%)** |
| Wrong-detail detection | **18/24 (75.0%)** |
| False refusal | **0/18** |
| Fabrication acceptance | **0/18** |
| Correct refusal | **27/27** |
| Half-true detection | **12/12 (100%)** |
| Stale detection | 6/12 (50.0%) |
| Clarification | 4/9 (44.4%) |
| URL provenance | 62/102 |
| Decisive evidence + correctness | 29/102 |

**All mandatory numerical guardrails pass, but two results are API fallbacks. The completed one-worker run below is the final measurement without API failures.** No improvement in any metric is attributed to the schema field. In particular, stale 6/12 does not establish a staleness improvement: no gate was implemented. All 102 results carry default status=unverified, as expected while the verifier does not set it; the frozen checker scores confidence/notes rather than typed status.

The response model remained `gpt-4o-mini-2024-07-18`; no sampling setting changed. Observed usage: **643,093 tokens**, estimated **$0.0768384** using the existing pricing file; mean case latency **4.01s**, p95 **6.24s**. Actual billing is NOT TESTED. The full suite's successful model responses were checked before accepting the measurement.

No source edits were made during this rerun. The existing **19/19 unit tests**, both saved-report HTTP rendering checks, and successful offline replay from this exact source revision remain the compatibility evidence; changing the user's local key does not alter those source files. The audit still identifies only the retained tools author payload and schema field as changes relative to the original task fingerprint. The peer's verifier and the eval cases/checkers remain untouched.

The schema field is shipped in **c31d683** and available for the other engineer's deterministic gate. Consumer gates and provenance remain unapplied.


### Final complete live measurement — one worker, three repeats

The three-worker attempt encountered two API token-rate-limit fallbacks. Its records were preserved. A new **complete** 102-case run, `codex-status-shipped-serial`, used **one worker** to lower request volume. No results were replaced selectively, and no model, sampling, source, prompt or checker setting changed.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/run.py --run-id codex-status-shipped-serial --repeats 3 --workers 1 --offline-sources
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/verification/eval/analyze.py --run-id codex-status-shipped-serial
```

[Summary](implementation/status_shipped_serial_summary.json), [audit](implementation/status_shipped_serial_audit.json), [raw records](eval/runs/codex-status-shipped-serial/). All 102 cases completed; **327 successful model responses, zero API-failure notes, zero harness exceptions**. Every result has default status=unverified, confirming the field is available but not yet set by the protected verifier.

| Metric | Final shipped-field run |
| --- | ---: |
| Correct verdict | **86/102 (84.3%)** |
| Wrong-detail detection | **20/24 (83.3%)** |
| False refusal | **0/18** |
| Fabrication acceptance | **0/18** |
| Correct refusal | **27/27** |
| Half-true detection | **12/12 (100%)** |
| Stale detection | 7/12 (58.3%) |
| Clarification | 2/9 (22.2%) |
| URL provenance | 64/102 |
| Decisive evidence + correctness | 29/102 |

Wrong-detail by repeat: **6/8, 8/8, 6/8**. All mandatory guardrails pass. Clarification is lower than the reproduced baseline's 5/9; it is explicitly reported rather than hidden. No metric increase or decrease is attributed to this post-response schema field; earlier identical-request replay demonstrated why it cannot cause those model-behavior differences. In particular, no deterministic stale gate was added and no stale-detection improvement is claimed.

Model: `gpt-4o-mini-2024-07-18`. Usage: **613,401 tokens**, estimated **$0.06234795** under the existing pricing file; mean case latency **3.82s**, p95 **6.03s**. Actual account billing remains NOT TESTED. The quota and rate-limit blocks on completing a live measurement are resolved for this run.

This documentation update changes no source. The one-line schema field remains committed in **c31d683**, with the previously recorded 19/19 unit tests, both saved-report server-rendering checks and successful no-key offline replay. The original CR-1 revert was not evidence of a code regression. The field is shipped and ready for the other engineer's deterministic staleness gate; consumer gates and provenance remain unapplied.
