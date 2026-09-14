# Live-run finding — cluster contamination

**Source:** live run over `test_signals_graded.json` (8 signals → 7 clusters).
**Observed:** 2026-09-13. **Re-verified:** 2026-09-14 against the merged tree — `clustering.py` is unchanged, and the contaminating merge still reproduces.
**Scope:** Report only. No code changed.

> This is the one finding from the original live run that is layer-independent and survives the merge that adopted DHM22's `evaluation.py` / `recommendation.py`. The other two original findings described behavior of the superseded agent implementations and no longer match the code.

---

## Cluster contamination — a fabricated claim becomes corroborating evidence

### Observed
Clustering merged two signals into one cluster (cluster 2):

| tier | signal |
|---|---|
| **primary** | "OpenTelemetry GenAI conventions define `invoke_agent`, `chat` and `execute_tool` spans for agent runs" (genuine) |
| **secondary** | "OpenTelemetry ships GenAI semantic conventions **v1.0 GA** with stable agent-graph and guardrail spans" (**fabricated** — the conventions are Development stability with no release) |

Because the two landed in one cluster, `TrendCluster.independent_source_count` reported **2 independent sources**, and the fabricated GA claim was presented to the verifier as a second, corroborating source. In the original run the verifier's note read:

> "…confirmed through a primary source describing their span definitions, **supported by a secondary news announcement regarding its general availability.**"

The fabricated "GA" claim did not merely survive verification — it acted as corroboration for a genuine but *distinct* signal, raising the verified confidence rather than lowering it.

The defect is that the input was contaminated **before** any agent saw it. Downstream agents behaved correctly on the input they were handed; this is why the finding is independent of which evaluation/recommendation implementation is in place.

### Owning layer
**Clustering** (`02_src/clustering.py`, `cluster_signals`). Pass 1 merges any two signals that share **≥1** rare identifier (`min_shared=1`). The two signals share topic-level vocabulary (`gen_ai`, "GenAI semantic conventions", "spans") but make *different claims* — one describes span definitions, the other asserts a v1.0 GA release. Same topic is not the same event, but a single shared identifier is enough to merge them, and the merge is then read downstream as independent corroboration.

### Smallest safe fix
Raise the cross-signal merge bar: require **≥2 shared rare identifiers** (`min_shared=2`) for signals from different sources/tiers to merge. This is a single existing parameter already threaded through `cluster_signals`, no new logic.

- **Why it's minimal:** one-parameter change; leaves genuine multi-identifier pairs (the `langchain.mcp` cross-source case this pass was built for) intact.
- **Trade-off to validate:** raising `min_shared` risks *under*-clustering genuine pairs that share only one strong identifier. Before adopting, re-run this file and confirm (a) the fabricated GA signal separates from the genuine one, and (b) any genuinely-same-event cross-source pairs still merge.
- **If that trade-off is unacceptable:** the larger alternative is to stop treating co-clustering as corroboration when a clustered secondary signal makes a *version/GA claim* the primary does not — i.e. pass such claims to the verifier as **claims to check**, not as supporting sources. That is a verification-contract change and out of scope for a minimal fix.
