#!/usr/bin/env python3
"""Run the frozen CurriculumAgent regression benchmark.

The evaluator constructs isolated, already-verified trends from benchmark
cases.  It never requires those synthetic cases to appear in the monitoring
signals file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "02_src"
sys.path.insert(0, str(SRC))

from agents import tools as agent_tools  # noqa: E402
from agents.curriculum import CurriculumAgent, CurriculumTrace  # noqa: E402
from clustering import cluster_signals  # noqa: E402
from schemas import CurriculumMatch, RawSignal, VerifiedTrend  # noqa: E402


class RecordingClient:
    """OpenAI client wrapper that forces temperature zero and counts tokens."""

    def __init__(self):
        from openai import OpenAI

        self._inner = OpenAI()
        self.chat = self
        self.tokens = 0

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        kwargs["temperature"] = 0
        reply = self._inner.chat.completions.create(**kwargs)
        usage = getattr(reply, "usage", None)
        self.tokens += int(getattr(usage, "total_tokens", 0) or 0)
        return reply


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


_VECTORSTORE_TRANSIENT_SUFFIXES = {"-wal", "-shm", ".wal", ".shm", ".lock"}


def vector_store_identity(path: Path, collection_name: str | None = None) -> dict:
    """Return a deterministic identity for persistent vector-store files.

    Relative POSIX paths are sorted and hashed together with each file's
    bytes. SQLite WAL/SHM/lock files are transient and excluded. When a
    collection name is supplied, its name and document count are validated
    before the persistent-file snapshot is taken.
    """
    validation = None
    if collection_name is not None:
        import chromadb

        collection = chromadb.PersistentClient(path=str(path)).get_collection(collection_name)
        validation = {
            "collection_name": collection.name,
            "document_count": collection.count(),
        }

    entries = []
    for file_path in path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.name.endswith(tuple(_VECTORSTORE_TRANSIENT_SUFFIXES)):
            continue
        relative = file_path.relative_to(path).as_posix()
        file_hash = sha256_file(file_path)
        entries.append({"path": relative, "sha256": file_hash, "size": file_path.stat().st_size})
    entries.sort(key=lambda item: item["path"])
    digest = hashlib.sha256()
    for item in entries:
        digest.update(item["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(item["sha256"]))
        digest.update(b"\n")
    result = {
        "identity_sha256": digest.hexdigest(),
        "persistent_files": entries,
        "excluded_transient_suffixes": sorted(_VECTORSTORE_TRANSIENT_SUFFIXES),
    }
    if validation is not None:
        result["collection_validation"] = validation
    return result


def benchmark_version(gold_path: Path, benchmark_data=None) -> str:
    """Read the benchmark version from its metadata, with v1 compatibility.

    Frozen benchmark files are case lists for backward compatibility, while
    newer benchmarks keep version metadata in the sibling manifest.  Older
    v1 inputs without a manifest retain the historical ``1.0`` fallback.
    """
    if isinstance(benchmark_data, dict) and benchmark_data.get("benchmark_version") is not None:
        return str(benchmark_data["benchmark_version"])
    manifest_path = gold_path.with_name(f"{gold_path.stem}_manifest.json")
    if manifest_path.is_file():
        try:
            manifest = load_json(manifest_path)
        except (OSError, json.JSONDecodeError):
            manifest = {}
        if isinstance(manifest, dict) and manifest.get("benchmark_version") is not None:
            return str(manifest["benchmark_version"])
    return "1.0"


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with open(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(name, path)
    except Exception:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def expected_locator(case: dict) -> int | None:
    return case.get("expected_slide_number", case.get("expected_cell_number"))


def structured_match_fields(match: CurriculumMatch | None) -> dict:
    if match is None:
        return {
            "week": None, "source_file": None, "locator": None,
            "content_type": None, "citation": None,
        }
    return {
        "week": match.week,
        "source_file": match.source_file,
        "locator": match.slide_number,
        "content_type": match.content_type,
        "citation": match.citation,
    }


def score_case(case: dict, match: CurriculumMatch | None, trace: CurriculumTrace) -> dict:
    """Score one output using structured gold fields, not citation formatting."""
    expected_affected = bool(case["expected_affected"])
    predicted_affected = match is not None
    decision_correct = predicted_affected == expected_affected
    output_schema_valid = match is None or isinstance(match, CurriculumMatch)
    expected = {
        "week": case.get("expected_week"),
        "source_file": case.get("expected_source_file"),
        "locator": expected_locator(case),
        "content_type": case.get("expected_content_type"),
    }
    acceptable_matches = case.get("acceptable_matches") or [expected]
    actual = structured_match_fields(match)
    source_correct = locator_correct = content_type_correct = False
    if expected_affected and match is not None:
        source_correct = any(actual["source_file"] == item.get("source_file")
                             for item in acceptable_matches)
        locator_correct = any(
            actual["week"] == item.get("week") and actual["locator"] == item.get("locator")
            for item in acceptable_matches
        )
        content_type_correct = any(actual["content_type"] == item.get("content_type")
                                   for item in acceptable_matches)
    complete_match = expected_affected and match is not None and any(
        actual["week"] == item.get("week")
        and actual["source_file"] == item.get("source_file")
        and actual["locator"] == item.get("locator")
        and actual["content_type"] == item.get("content_type")
        for item in acceptable_matches
    )
    strict = decision_correct and (not expected_affected or complete_match)
    if not output_schema_valid:
        reason = "invalid CurriculumMatch output type"
    elif not decision_correct:
        reason = "affected decision mismatch"
    elif expected_affected and not complete_match and not source_correct:
        reason = "source_file mismatch"
    elif expected_affected and not complete_match and not locator_correct:
        reason = "week or slide/page/cell locator mismatch"
    elif expected_affected and not complete_match and not content_type_correct:
        reason = "content_type mismatch"
    elif expected_affected and complete_match:
        reason = "correct acceptable structured match"
    else:
        reason = "correct structured match" if expected_affected else "correct abstention"
    return {
        "id": case["id"],
        "title": case["title"],
        "expected_affected": expected_affected,
        "predicted_affected": predicted_affected,
        "decision_correct": decision_correct,
        "output_schema_valid": output_schema_valid,
        "expected_fields": expected,
        "acceptable_matches": acceptable_matches,
        "predicted_fields": actual,
        "acceptable_citations": case.get("acceptable_citations", []),
        "citation_for_reporting": actual["citation"],
        "strict_match": strict,
        "source_correct": source_correct if expected_affected else None,
        "locator_correct": locator_correct if expected_affected else None,
        "content_type_correct": content_type_correct if expected_affected else None,
        "pass": strict,
        "pass_reason": reason,
        "reason": trace.reason,
        "search_step_count": len(trace.steps),
    }


def make_trend(case: dict) -> VerifiedTrend:
    signal = RawSignal(
        title=case["title"],
        source="curriculum_benchmark_v1",
        source_tier="primary",
        summary=case.get("description", case["title"]),
        url="",
        published="",
    )
    cluster = cluster_signals([signal])[0]
    return VerifiedTrend(
        cluster=cluster,
        confidence=1.0,
        verification_note="verification bypassed for isolated CurriculumAgent evaluation",
        evidence=[],
    )


def mean_metric(runs: list[dict], name: str) -> float | None:
    values = [r[name] for r in runs if r.get(name) is not None]
    return sum(values) / len(values) if values else None


def run_repeat(gold_cases: list[dict], db: Path, model: str, repeat: int) -> dict:
    original_search = agent_tools.search_curriculum

    def search_clean_db(question, week=None, max_results=3, db_path=None, content_type=None):
        return original_search(
            question=question, week=week, max_results=max_results,
            db_path=str(db),
        )

    agent_tools.TOOL_FUNCTIONS["search_curriculum"] = search_clean_db
    client = RecordingClient()
    agent = CurriculumAgent(client=client, model=model)
    cases = []
    started = time.perf_counter()
    for case in gold_cases:
        case_started = time.perf_counter()
        before_tokens = client.tokens
        trace = CurriculumTrace()
        try:
            match = agent.run(make_trend(case), trace)
            error = None
        except Exception as exc:  # evaluator records a failed case, then continues
            match = None
            error = f"agent exception: {exc}"
            trace.reason = error
        scored = score_case(case, match, trace)
        scored["elapsed_seconds"] = time.perf_counter() - case_started
        scored["token_usage"] = client.tokens - before_tokens
        scored["error"] = error
        cases.append(scored)
    elapsed = time.perf_counter() - started
    negatives = [c for c in cases if not c["expected_affected"]]
    positives = [c for c in cases if c["expected_affected"]]
    return {
        "repeat": repeat,
        "cases": cases,
        "overall_strict_score_percent": 100 * sum(c["strict_match"] for c in cases) / len(cases),
        "decision_accuracy_percent": 100 * sum(c["decision_correct"] for c in cases) / len(cases),
        "affected_detection_rate_percent": 100 * sum(c["predicted_affected"] for c in positives) / len(positives),
        "correct_abstention_rate_percent": 100 * sum(not c["predicted_affected"] for c in negatives) / len(negatives),
        "false_positive_rate_percent": 100 * sum(c["predicted_affected"] for c in negatives) / len(negatives),
        "positive_source_accuracy_percent": 100 * sum(c["source_correct"] for c in positives) / len(positives),
        "positive_locator_accuracy_percent": 100 * sum(c["locator_correct"] for c in positives) / len(positives),
        "positive_content_type_accuracy_percent": 100 * sum(c["content_type_correct"] for c in positives) / len(positives),
        "positive_strict_match_rate_percent": 100 * sum(c["strict_match"] for c in positives) / len(positives),
        "ocr_subset_score_percent": 100 * sum(c["strict_match"] for c in cases if next(x for x in gold_cases if x["id"] == c["id"]).get("subset") == "ocr") / max(1, sum(1 for x in gold_cases if x.get("subset") == "ocr")),
        "output_schema_validity_percent": 100 * sum(c["output_schema_valid"] for c in cases) / len(cases),
        "total_tokens": client.tokens,
        "execution_time_seconds": elapsed,
    }


def markdown_summary(result: dict) -> str:
    m = result["metrics"]

    def format_metric(name: str) -> str:
        value = m.get(name)
        if isinstance(value, dict):
            mean = value.get("mean")
            std = value.get("std", 0.0)
        else:
            mean = value
            std = 0.0
        if mean is None:
            return "n/a"
        return f"{float(mean):.2f}% ± {float(std or 0.0):.2f}"

    lines = [
        "# CurriculumAgent Regression Benchmark v1",
        "",
        f"- Label: {result['label']}",
        f"- Benchmark: {result['benchmark_version']} ({result['case_count']} cases)",
        f"- Model: {result['model']}",
        f"- Repeats: {result['repeats']}",
        "",
        f"- Overall strict score: {format_metric('overall_strict_score_percent')}",
        f"- Decision accuracy: {format_metric('decision_accuracy_percent')}",
        f"- Affected detection rate: {format_metric('affected_detection_rate_percent')}",
        f"- Correct abstention rate: {format_metric('correct_abstention_rate_percent')}",
        f"- False-positive rate: {format_metric('false_positive_rate_percent')}",
        f"- OCR subset score: {format_metric('ocr_subset_score_percent')}",
        f"- Output schema validity: {format_metric('output_schema_validity_percent')}",
        f"- Total tokens: {result['total_tokens']}",
        f"- Execution time: {result['execution_time_seconds']:.2f}s",
        "",
        "Detailed JSON: " + result["detailed_output"],
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run frozen CurriculumAgent regression benchmark")
    parser.add_argument("--signals", type=Path, default=None, help="legacy input; benchmark cases are self-contained")
    parser.add_argument("--gold", type=Path, default=ROOT / "evals/curriculum_benchmark_v1.json")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--label", default="v0")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args()

    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    if args.out.exists() or args.summary_out.exists():
        raise SystemExit("Refusing to overwrite an existing result or summary output")
    if not args.gold.is_file():
        raise SystemExit(f"gold file not found: {args.gold}")
    benchmark_cases = load_json(args.gold)
    if not isinstance(benchmark_cases, list) or not benchmark_cases:
        raise SystemExit("gold file must contain a non-empty case list")
    benchmark_hash = sha256_file(args.gold)
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not loaded")

    sqlite_path = args.db / "chroma.sqlite3"
    all_runs = []
    original_search = agent_tools.search_curriculum
    started = time.perf_counter()
    try:
        for repeat in range(1, args.repeats + 1):
            all_runs.append(run_repeat(benchmark_cases, args.db, args.model, repeat))
    finally:
        agent_tools.TOOL_FUNCTIONS["search_curriculum"] = original_search
    total_elapsed = time.perf_counter() - started
    store_identity = vector_store_identity(args.db, "wecloud_curriculum")
    metric_names = [
        "overall_strict_score_percent", "decision_accuracy_percent",
        "affected_detection_rate_percent", "correct_abstention_rate_percent",
        "false_positive_rate_percent", "positive_source_accuracy_percent",
        "positive_locator_accuracy_percent", "positive_content_type_accuracy_percent",
        "positive_strict_match_rate_percent", "ocr_subset_score_percent",
        "output_schema_validity_percent",
    ]
    metrics = {name: {"mean": mean_metric(all_runs, name), "std": statistics.pstdev([r[name] for r in all_runs]) if len(all_runs) > 1 else 0.0} for name in metric_names}
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "label": args.label,
        "benchmark_version": benchmark_version(args.gold, benchmark_cases),
        "benchmark_sha256": benchmark_hash,
        "model": args.model,
        "temperature": 0,
        "repeats": args.repeats,
        "case_count": len(benchmark_cases),
        "positive_case_count": sum(bool(c["expected_affected"]) for c in benchmark_cases),
        "negative_case_count": sum(not bool(c["expected_affected"]) for c in benchmark_cases),
        "vector_store_path": str(args.db),
        "vector_store_sha256": store_identity["identity_sha256"],
        "vector_store_identity": store_identity,
        "metrics": metrics,
        "total_tokens": sum(r["total_tokens"] for r in all_runs),
        "execution_time_seconds": total_elapsed,
        "runs": all_runs,
        "detailed_output": str(args.out),
        "summary_output": str(args.summary_out),
    }
    atomic_write(args.out, json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    atomic_write(args.summary_out, markdown_summary(result))
    print(f"Overall strict score: {metrics['overall_strict_score_percent']['mean']:.2f}%")
    print(f"Cases: {len(benchmark_cases)}")
    print(f"Total tokens: {result['total_tokens']}")
    print(f"Output path: {args.out}")


if __name__ == "__main__":
    main()
