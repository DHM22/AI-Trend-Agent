# CurriculumAgent Evaluation Summary

## Scope

This contribution prepares the CurriculumAgent work for the proposed branch `feat/curriculum-agent-improvements`. The branch has not been created, and nothing has been staged, committed, or pushed.

The evaluated scope is limited to:

- Curriculum RAG ingestion.
- Hybrid OCR V2.
- Combined native PDF text and image-text extraction.
- Text normalization, cleanup, and native/OCR line deduplication without rewriting technical identifiers.
- Retrieval V2, combining semantic and deterministic lexical ranking with Reciprocal Rank Fusion (RRF).
- CurriculumAgent Prompt V3.
- The frozen 24-case Curriculum benchmark v1.1: 12 positive and 12 negative cases.

## Version progression

| Version | Main Improvement | Previous Score | New Score | Improvement |
|---|---|---:|---:|---:|
| V0 | Baseline before OCR | — | 41.67% | Baseline |
| V1 | Initial OCR support | 41.67% | 45.83% | +4.16 percentage points |
| V2 | Semantic + lexical RRF retrieval | 45.83% | 75.00% | +29.17 percentage points |
| V3 | CurriculumAgent Prompt V3 | 75.00% | 79.17% | +4.17 percentage points |
| V4 | Hybrid OCR V2 | 79.17% | 87.50% | +8.33 percentage points |

From V0 to V4, the strict score increased from **41.67% to 87.50%**:

- Total improvement: **+45.83 percentage points**.
- Relative improvement: **approximately 110%**.
- Strict passes increased from approximately **10/24 to 21/24**.

## Final V4 metrics

| Metric | V4 result |
|---|---:|
| Strict score | 87.50% |
| Decision accuracy | 100% |
| Affected detection rate | 100% |
| Correct abstention rate | 100% |
| False-positive rate | 0% |
| OCR subset score | 100% |
| Output schema validity | 100% |
| Positive source accuracy | 91.67% |
| Positive locator accuracy | 75% |
| Total tokens | 98,843 |
| Execution time | 129.99 seconds |

The V4 run used `gpt-4o-mini`, temperature `0`, one repeat, frozen benchmark v1.1, and `vectorstore_v2_hybrid_ocr`.

## Remaining strict mismatches

All **24/24 affected/unaffected decisions were correct**. The three failures below failed only the frozen benchmark's strict structured citation match.

| Case | Decision | Strict citation mismatch |
|---|---|---|
| CURR-012 | Correctly predicted affected | Slide 28 was selected instead of accepted slide 27. |
| CURR-015 | Correctly predicted affected | A relevant alternative lab was selected, but it is not accepted by the frozen gold. |
| CURR-016 | Correctly predicted affected | Cell 6 was selected instead of accepted cell 8. |

These are citation/source-locator mismatches, not affected/unaffected classification errors.

## Main implementation and evaluation files

| File | Role |
|---|---|
| `02_src/curriculum_ingest.py` | Curriculum ingestion, Hybrid OCR V2, normalization, deduplication, provenance metadata, lexical ranking, and RRF retrieval. |
| `02_src/agents/curriculum.py` | CurriculumAgent and Prompt V3 causal-impact, evidence, abstention, identifier-preservation, and prompt-injection rules. |
| `evals/curriculum_benchmark_v1_1.json` | Frozen 24-case benchmark. |
| `evals/curriculum_benchmark_v1_1_manifest.json` | Benchmark version, counts, frozen status, and SHA-256 metadata. |
| `evals/run_curriculum_eval.py` | Curriculum-only evaluation runner, deterministic temperature setting, scoring, token accounting, and result writing. |
| `evals/test_hybrid_ocr_v2.py` | Offline tests for OCR triggering, merging, cleanup, deduplication, provenance, and identifier preservation. |
| `evals/test_curriculum_eval_metadata.py` | Evaluator benchmark-version and metadata compatibility tests. |
| `evals/curriculum_prompt_v3_manifest.json` | Prompt V3 scope and validation record. |
| `evals/vectorstore_v2_hybrid_ocr_manifest.json` | Hybrid OCR implementation, local-store identity, corpus counts, provenance counts, and quality validation. |
| `evals/results/hybrid_ocr_v2_comparison.md` | Native/OCR/Hybrid OCR text-quality comparison. |
| `evals/results/curriculum_v1_vs_v2_hybrid_ocr_retrieval_comparison.md` | Offline Retrieval V2 comparison between the V1 and V2 stores. |
| `evals/results/curriculum_v4_hybrid_ocr_2026-09-20.json` | Detailed V4 case traces and aggregate metrics. |
| `evals/results/curriculum_v4_hybrid_ocr_2026-09-20_summary.md` | Concise V4 metrics summary. |

The Chroma directory `vectorstore_v2_hybrid_ocr/` is a local evaluation dependency, not branch content.

## PowerShell reproduction command

The V4 metadata corresponds to the following PowerShell command. `CurriculumAgent` loads a local `.env` when present; the file and its API key must remain local and must never be committed or printed.

```powershell
Set-Location -LiteralPath 'C:\Users\PC\Documents\ChatGPT\AI-Trend-Agent-Latest'

py -3.11 .\evals\run_curriculum_eval.py `
  --gold .\evals\curriculum_benchmark_v1_1.json `
  --db .\vectorstore_v2_hybrid_ocr `
  --model gpt-4o-mini `
  --repeats 1 `
  --label v4_hybrid_ocr `
  --out .\evals\results\curriculum_v4_hybrid_ocr_2026-09-20.json `
  --summary-out .\evals\results\curriculum_v4_hybrid_ocr_2026-09-20_summary.md
```

This command was documented only and was not executed during branch preparation. A future rerun should use new output filenames rather than overwrite the preserved V4 artifacts.

## Safety and exclusions

The Curriculum contribution must contain:

- No `.env` file or API key.
- No Chroma or vector-store directory.
- No cache, `__pycache__`, temporary file, or local OCR artifact.
- No VerificationAgent, RecommendationAgent, or end-to-end implementation or evaluation work.

The branch should contain source, tests, frozen benchmark metadata, manifests, and approved evaluation reports only. Generated local stores and raw/local working artifacts remain dependencies outside Git.

## Git preflight

### Repository state

| Item | Read-only inspection result |
|---|---|
| Current branch | `feature/ruyuf-improvements` |
| Proposed branch | `feat/curriculum-agent-improvements` — not created |
| Fetch remote | `origin https://github.com/DHM22/AI-Trend-Agent.git` |
| Push remote | `origin https://github.com/DHM22/AI-Trend-Agent.git` |
| Staging | Nothing staged by this preparation task |
| Commit/push/history changes | None |

### `git status --short` before this summary was created

```text
 M 02_src/agents/curriculum.py
 M 02_src/agents/recommendation.py
 M 02_src/agents/verification.py
 M 02_src/curriculum_ingest.py
?? 01_data/CURRICULUM_DATA_MANIFEST.md
?? 01_data/_excluded_duplicates/
?? evals/
?? test_signals_graded.json
?? vectorstore_v0_before_ocr/
?? vectorstore_v1_after_ocr/
?? vectorstore_v2_hybrid_ocr/
```

After this task, `review/curriculum/EVALUATION_SUMMARY.md` is also an untracked Curriculum documentation file.

### Changed or untracked Curriculum-relevant files

The working tree contains two tracked Curriculum implementation changes:

| File | Working-tree change |
|---|---|
| `02_src/agents/curriculum.py` | 59 added and 35 removed lines; Prompt V3 and CurriculumAgent behavior. |
| `02_src/curriculum_ingest.py` | 324 added and 36 removed lines; Hybrid OCR V2 and Retrieval V2. |

The following untracked files or groups are relevant candidates for a carefully scoped Curriculum contribution:

- `review/curriculum/EVALUATION_SUMMARY.md`.
- `01_data/CURRICULUM_DATA_MANIFEST.md` as corpus inventory documentation; no curriculum binary/source files should accompany it.
- Final frozen benchmark and manifest: `evals/curriculum_benchmark_v1_1.json` and `evals/curriculum_benchmark_v1_1_manifest.json`.
- Curriculum runner and focused tests: `evals/run_curriculum_eval.py`, `evals/test_curriculum_eval_metadata.py`, and `evals/test_hybrid_ocr_v2.py`.
- Prompt and store manifests: `evals/curriculum_prompt_v3_manifest.json` and `evals/vectorstore_v2_hybrid_ocr_manifest.json`.
- Approved Curriculum-only reports and the preserved V4 JSON/summary listed in the main-files table.

Older drafts, reviews, superseded benchmarks, legacy results, invalid-empty-store fixtures, and intermediate diagnostics should be reviewed individually rather than included through a broad `git add evals/`.

### Unrelated files that must not be included

- `02_src/agents/recommendation.py`.
- `02_src/agents/verification.py`.
- `test_signals_graded.json`.
- `01_data/_excluded_duplicates/` and its raw notebook artifact.
- `vectorstore_v0_before_ocr/`, `vectorstore_v1_after_ocr/`, and `vectorstore_v2_hybrid_ocr/`.
- End-to-end benchmark, runner, results, readiness, and adjudication files under `evals/`.
- Recommendation plan-safety and VerificationAgent tool-boundary manifests, tests, and results.
- `evals/run_end_to_end_eval.py`, `evals/test_end_to_end_eval.py`, `evals/run_eval.py`, VS Code demo results, and unrelated vector-store test fixtures.
- Any `.env`, API key, cache, `__pycache__`, temporary file, or local OCR image/text artifact.

### `.gitignore` audit

| Artifact | Excluded now? | Evidence / limitation |
|---|---|---|
| `.env` | Yes | `.gitignore` contains `.env`. |
| `__pycache__` and Python bytecode | Yes | Rules include `__pycache__/`, `*.pyc`, and `*.py[cod]`. |
| Literal `vectorstore/` | Yes | `.gitignore` contains `vectorstore/`. |
| Versioned `vectorstore_v*` directories | **No** | The current rule does not match `vectorstore_v0_before_ocr/`, `vectorstore_v1_after_ocr/`, or `vectorstore_v2_hybrid_ocr/`; Git reports them as untracked. They must be explicitly excluded from branch selection. |
| Curriculum tool cache | Yes | `01_data/.tool_cache/` is ignored. |
| Generic `.cache/`, `cache/`, temporary, and local OCR artifacts | **No general rule** | No broad cache/temp/OCR rule exists; these must be excluded explicitly unless `.gitignore` is separately hardened. |

Because several relevant and unrelated files share the untracked `evals/` directory, staging must use exact paths. Do not use `git add .`, `git add -A`, or `git add evals/` for this contribution.

CURRICULUM BRANCH CONTENT PREPARED — GIT PREFLIGHT COMPLETE — NOTHING STAGED OR PUSHED
