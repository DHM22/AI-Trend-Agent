# Verifier diagnosis: v2 dev

The current verifier performs external GitHub checks and calls an LLM when a client is available. Its confidence is a discrete Python decision tree over a narrow set of tool-derived facts. It cannot generally establish whether a release's claimed features are true. This limited evidence coverage, unreachable corroboration branches, and cluster-level scoring explain why genuine and fabricated claims can receive similar confidences.

Scope: static inspection of the current working tree and the explicitly dev-only results `results/v2_dev_baseline.json` and `results/v2_dev_iter.json`. No dataset file was opened, no test-split data or results were inspected, and no agents, evaluations, network checks, or tests were run. This report is the only file written. Examples below describe claim categories, not asserted identities of individual dev errors.

## 1. Inputs, rules, ceilings, and score movement

References: `02_src/agents/verification.py:309–350, 547–708, 750–882`.

There are **no additive feature weights** in verification confidence. `_base_confidence()` takes the first matching branch, `_enforce_bands()` clamps it, then injection and contradiction gates can lower it. The following deltas compare each branch with the unresolved default of 0.40; they are not independently additive.

| Priority | Condition | Base confidence | Change from 0.40 | Reachability through the current accumulator |
|---|---|---:|---:|---|
| 1 | Named repository missing | 0.15 | −0.25 | Reachable |
| 2 | Relevant claimed release missing | 0.20 | −0.20 | Reachable |
| 3 | At least two verified sources and a confirmed release | 0.95 | +0.55 | Unreachable |
| 4 | At least two verified sources, no confirmed release | 0.80 | +0.40 | Unreachable |
| 5 | One verified source and a confirmed release | 0.75 | +0.35 | Reachable |
| 6 | One verified source, no confirmed release | 0.60 | +0.20 | Unreachable |
| 7 | Confirmed release, without a verified source | 0.75 | +0.35 | Reachable for non-`github` signals |
| 8 | Repository exists, release not confirmed | 0.45 | +0.05 | Reachable |
| 9 | Otherwise unresolved | 0.40 | 0 | Reachable |

Confirming a release can therefore move a repo-only claim from 0.45 to 0.75 (+0.30); a missing release can move it to 0.20 (−0.25). Missing-release precedence can reduce an otherwise release-confirmed cluster from 0.75 to 0.20 if another claimed version remains missing.

How those facts are derived:

- **Repository identity:** `_claim_query()` extracts `owner/repo` from an actual `github.com` URL first, then a `github` source's `owner/repo: ...` title, otherwise the first product-like token in the title. The product regex recognizes dotted/hyphenated/underscored identifiers and mixed-case names, with a four-character minimum. It does not search summary text for a repository. `_repo_matches()` requires exact owner/name for qualified queries, or an exact repository basename for bare queries.
- **Repository found/missing:** a matching `github_lookup` result adds a confirmed repository. An error-free lookup with no match counts as missing only for an explicit owner/name present in the signals. A bare-name miss does not count. `repo_missing` is true only when a named miss exists **and no repository anywhere in the cluster was confirmed**. Conversely, a successful agent-written query need only match its result, not the signal; an unrelated model lookup can set `repo_exists` and suppress a named-missing result.
- **Version identity:** use a decoded GitHub release URL tag, otherwise the first version-bearing token after a GitHub title's colon, otherwise the first `v?major.minor[.patch]` in title or summary. Normalization lowercases and strips a leading `v`.
- **Release confirmed:** the tool must return a non-error `matched_release` with the requested normalized tag. The requested repo and version must match at least one signal's extracted claim. `claim_verified` means **at least one release tag exists**, not that every signal or feature is true.
- **Release missing:** a relevant, non-error result must explicitly say `release_found=False` and identify the requested repository. Missing repo/version pairs subsequently confirmed are removed. A remaining missing pair activates the 0.20 branch.
- **Verified sources:** only signals with `source == "github"` and a confirmed matching release are marked verified. Counting distinct `e.source` values then produces only 0 or 1, because all eligible values are literally `github`. Thus the two-source branches cannot execute. One verified source necessarily implies `claim_verified`, making the 0.60 branch unreachable too. Additional GitHub repositories do not add independent sources; blogs and discussion links never count as verified sources.

| Post-score rule | Effect | Maximum reduction under current reachable scores |
|---|---|---:|
| Named missing repo ceiling | `min(score, 0.30)` | 0: the preceding branch already returns 0.15 |
| Fewer than two verified sources | `min(score, 0.75)` | 0: every reachable base score is already ≤0.75 |
| Clamp and rounding | Clamp to [0,1], round to two decimals | 0 for the fixed constants |
| Injection marker | `min(score, 0.10)` | 0.65, from 0.75 |
| Proven stale “latest” claim | Force 0.00 and `status="contradicted"` | 0.75 |
| Proven publisher mismatch | Force 0.00 and `status="contradicted"` | 0.75 |

The missing-repo and single-source ceilings would reduce hypothetical supplied scores by `max(0, score−ceiling)`; they add no reduction along the normal current decision tree. Multiple gates are not additive.

Injection scans the complete representative title and every signal title/summary, including beyond the LLM's truncation. It recognizes “ignore/disregard previous/prior instructions” with optional “all/the”, “system override”, and opening/closing system tags. It does not implement general semantic injection detection or scan signal URLs for these markers.

The staleness gate requires a regex-recognized affirmative latest/current-release assertion and a bound numeric version. It ignores nearby negations, limits “no newer release” to a version within 40 characters, and needs a repo extracted from source metadata or a GitHub URL. It calls `verify_release` for that version and a release listing. Only a later-dated stable release, no later than an explicit `as of YYYY-MM-DD` or today's date, forces zero. Missing/error payloads, no matched claimed release date, or no qualifying newer release do nothing. It compares publication dates, not semantic version order. The signal's `published` field is not used. These extra gate calls append reasoning but do not re-accumulate positive scoring facts.

The publisher gate requires a named account in supported “published by” or publisher/maintainer/author-is wording, an extracted repo, the first numeric version in claim text, and a validated author already collected for that same repo/version. A case-insensitive mismatch forces zero. Unknown authors and unrecognized claims have no effect. Both gates inspect combined cluster text and can therefore bind information across sibling signals.

**Zero direct weight:** stars, repository description, last-push date, prose plausibility, LLM conclusions, number of tool calls, round exhaustion, raw signal count, declared independent-source count, and current `source_tier`. Source tier appears in the prompt and note but not the current numeric tree. Release dates/authors affect only the narrow gates above. Titles, summaries, URLs, and source labels affect extraction and tool selection. LLM summary input is truncated to 400 characters per signal; deterministic regex checks use full text.

## 2. External checks and fabricated claims it cannot establish

References: `02_src/agents/tools.py:69–123, 144–202, 237–332`; `verification.py:363–507`.

**Yes, actual lookup implementations exist:** repository search calls GitHub `/search/repositories`; release verification calls `/repos/{repo}/releases/tags/{tag}` with exact/bare/`v` variants, then `/repos/{repo}/releases` when necessary. These are requests executed by Python, not simulated model answers.

Successful results are cached on disk. By default there is no expiry; `TOOL_CACHE_TTL` can impose one. `TOOL_CACHE_ONLY` serves cache entries and returns an unchecked error on misses without networking. Rate limits and network errors are not negative evidence. The saved dev JSON does not record cache mode or responses, so it cannot prove which calls hit live GitHub in that run. I did not execute these tools because they can write cache files.

Coverage limits:

- **Invented capabilities attached to a real release:** a fabricated API, feature, benchmark, security guarantee, integration, or performance improvement can share the same repo/tag as a genuine claim and receive 0.75. The release tool discards the release body; it returns tag, name, author, publication date, URL and prerelease flag. The scorer does not compare even the returned name against the feature assertion. Source truth differing only in feature prose is therefore not independently tested.
- **Fabricated blog/news/discussion content:** there is no general URL fetcher, web search, blog-page checker, or discussion-source corroborator offered to the verifier. It cannot validate whether a non-GitHub announcement page exists or contains the claim. Genuine and fabricated non-release announcements can both remain at 0.40/0.45.
- **Invented product identified only by a bare name:** a search miss leaves it unresolved rather than setting `repo_missing`; a same-named repository under another owner can satisfy basename matching. An explicitly named owner/repo is substantially more checkable.
- **Claims beyond the narrow gates:** unsupported author wording, unbound versions, missing author metadata, or stale claims outside the recency patterns cannot be reliably contradicted by those gates. Old-but-real releases are intentionally not penalized merely for age.

These are evidence blind spots, not a claim that such items can never accidentally receive low confidence: an unrelated injection marker or missing tag can still lower the score. The missing factual assertion itself is not checked.

Repository search defaults to the top three hits sorted by stars, rather than an exact repository endpoint. Release history requests eight entries and returns five, without pagination. These limits and indefinitely cached observations can cause missed matches or missed newer releases; release-list fallback also never promotes a listed tag to `matched_release`. External lookup capability does not guarantee complete evidence.

## 3. LLM usage and the ~120k tokens

References: `04_eval/run_eval.py:89–110, 186–227`; `verification.py:363–413`; `curriculum.py:214–273`; `evaluation.py:265–307`; `recommendation.py:355–403`.

The dev baseline records **122,487 total tokens**, 32 signals, 26 clusters, and one repeat with observed model `gpt-4o-mini-2024-07-18`. The dev iteration records 131,758 tokens. The runner shares one `RecordingClient` across all four agents and totals `usage.total_tokens` from their chat-completion responses.

| Agent | What uses the model | Confidence effect |
|---|---|---|
| Verification | Up to six calls per cluster to choose tools, arguments, follow-ups and stopping | Indirect: changes the facts gathered; no model-supplied numeric score is accepted |
| Curriculum | Up to four tool-loop calls plus a final completion to search/select curriculum evidence | None on the already-produced verification confidence |
| Evaluation | One rationale call when a curriculum match exists; otherwise template | None; maturity/relevance/total are computed in Python |
| Recommendation | One action-plan call for non-`watch` tiers; otherwise template | None; copies the trend's confidence |

The runner processes all four agents for every cluster even though the last three evaluation-layer scores are null. Repeated loop requests resend accumulating context and tool results. Token usage can therefore be substantial without richer verification scoring. Clustering is deterministic; the default curriculum retrieval uses local Chroma embeddings and is not part of this chat-token counter.

**Exact per-agent allocation is unavailable.** Saved results have neither per-agent usage counters nor call traces. They establish the aggregate, not how many tokens each agent actually consumed; Evaluation and Recommendation usage additionally depends on their conditions above.

The verifier really calls `client.chat.completions.create(... tools=..., tool_choice="auto", temperature=0, parallel_tool_calls=False)`. Its model prose is recorded as reasoning, not interpreted as a truth verdict. However, “the model has no effect on confidence” would be wrong: choosing or skipping a release lookup, choosing different arguments, or stopping early changes accumulated evidence. Without a client, or on loop failure, the scripted loop gathers facts instead. Both paths share the scorer, but their scores are guaranteed identical only when their resulting facts and gate results are equivalent.

## 4. Why the gap is small

The baseline's **0.082745 gap is the difference between the genuine and fabricated class means**, not the entire confidence range. Its MAE is 0.2484375 and accuracy is 0.59375. The iteration's gap is 0.041569, MAE 0.2703125, and accuracy 0.53125. Neither artifact contains individual confidences, so a precise histogram or attribution of each failure cannot be recovered from them.

The code supplies several mechanisms for overlap:

1. Current normal outputs are restricted to **0.15, 0.20, 0.40, 0.45, 0.75**, plus **0.10/0.00** for gates. Arbitrarily different evidence quality within a bucket has no numerical effect.
2. Uncheckable genuine announcements stay near 0.40–0.45, while fabricated feature claims on real releases can reach 0.75. The score tracks release existence more reliably than full claim truth.
3. The multi-source branches are unreachable. More corroborating prose or links cannot lift a genuine claim above 0.75, while missing checks cannot distinguish falsehood from insufficient evidence.
4. Cluster-level facts use “any release confirmed” and share one confidence across all members. The dev artifact reports contamination 0.1153846 across 26 clusters: **three mixed genuine/fabricated clusters**. `verification_metrics()` assigns that identical cluster score to each constituent signal, directly preventing separation within those clusters. Missing-release and injection/contradiction gates can also lower genuine siblings together with fabricated ones.
5. Network/cache failures and model stopping can leave many claims in the same unresolved branch. This is a plausible contributor, not a demonstrated event in the saved runs because tool traces were not saved.

The displayed verification score is also not accuracy: `verification_metrics()` computes `50 × (gap + 1 − MAE)`, yielding **41.7154/100** for the baseline. Accuracy separately uses a 0.50 threshold. A current unresolved score of 0.40/0.45 predicts fabricated even when the item is genuinely true but cannot be checked. The baseline gold gap is 0.577843, so even exact agreement with gold confidences would score 78.8922 under this formula.

For completeness, eval layer weights are clustering 0.20, verification 0.25, curriculum 0.15, evaluation 0.20, recommendation 0.20. They affect only the composite, not confidence. Since only the first two layer scores exist, their effective composite weights are 4/9 and 5/9.

## Historical attribution limit

Both dev artifacts record commit `f7c825d682ffdc573975ca2bb2b13b8db4169331` with `dirty: true`. The inspected verifier also has pre-existing uncommitted changes. The artifacts do not preserve those patches, so their names/timestamps cannot identify the exact scoring code used in either run.

The current diff against HEAD is material: HEAD awarded 0.60 to an unchecked first-party non-GitHub source (+0.20 over unresolved secondary), otherwise 0.50 for a real repo or declared primary tier (+0.10), and counted GitHub repository existence as source verification. It lacked the new 0.20 missing-release branch and the current release-relevance validation. It also rejected bare-name matches for secondary-only clusters and could classify bare-name misses there as missing. The current working tree removes those source-tier scoring shortcuts and changes repo/tag extraction and release checks. These older shortcuts could collapse genuine and fabricated first-party-looking claims into the same score, but assigning them to the baseline specifically would require the run's missing source snapshot.

The diagnosis is therefore strongest at the architectural level: narrow fact checking, discrete scores, ineffective multi-source corroboration, and shared cluster scores. No fixes were made, and no test split was accessed.
