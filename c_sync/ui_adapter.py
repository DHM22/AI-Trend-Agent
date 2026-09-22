"""Read-only bridge to the existing AI Trend Agent checkout.

The recorded run is the default data source. Evaluation and recommendation
always use the original agent classes; this module contains no scoring rules.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


DEFAULT_BACKEND = Path(__file__).resolve().parents[2] / "AI-Trend-Agent"
BACKEND = Path(os.environ.get("SKILLRADAR_BACKEND", DEFAULT_BACKEND)).expanduser().resolve()
SRC = BACKEND / "02_src"


def backend_ready() -> bool:
    return (SRC / "schemas.py").is_file() and (SRC / "agents" / "evaluation.py").is_file()


def _imports() -> None:
    if not backend_ready():
        raise FileNotFoundError(f"AI Trend Agent backend not found at {BACKEND}")
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))


def load_recorded_run() -> tuple[dict, list]:
    """Load the actual saved agent output and source signals without network calls."""
    _imports()
    from clustering import load_signals
    from demo_snapshot import load_snapshot

    snapshot = load_snapshot(str(BACKEND / "01_data" / "demo_snapshot.json"))
    signals = load_signals(str(BACKEND / "01_data" / "signals.json"))
    return snapshot, signals


def extract_upload(name: str, contents: bytes) -> list:
    """Route a user upload through the project's existing format extractors."""
    _imports()
    from tempfile import NamedTemporaryFile
    from curriculum_ingest import extract_ipynb, extract_pdf, extract_pptx, topic_from_filename

    suffix = Path(name).suffix.lower()
    extractor = {".pdf": extract_pdf, ".pptx": extract_pptx, ".ipynb": extract_ipynb}.get(suffix)
    if extractor is None:
        raise ValueError("Supported files: PDF, PPTX, and IPYNB.")
    # Named files in the writable UI workspace also work in restricted Windows
    # environments where newly created temporary directories deny child writes.
    with NamedTemporaryFile(dir=Path(__file__).resolve().parent,
                            prefix=".skillradar-upload-", suffix=suffix,
                            delete=False) as temporary:
        path = Path(temporary.name)
        temporary.write(contents)
    try:
        chunks = extractor(path, None)
        original_topic = topic_from_filename(Path(name))
        for chunk in chunks:
            chunk.topic = original_topic
            chunk.source_file = Path(name).name
        return chunks
    finally:
        path.unlink(missing_ok=True)


class _OfflineCompletions:
    def create(self, **_kwargs):
        raise RuntimeError("Offline replay: model calls are disabled")


class _OfflineChat:
    completions = _OfflineCompletions()


class _OfflineClient:
    chat = _OfflineChat()


def evaluate_record(record: dict, signals: list) -> tuple:
    """Rehydrate saved agent inputs and invoke the validated original agents.

    The snapshot has no individual evaluation scores, so the original
    EvaluationAgent calculates them from its saved verified trend and match.
    Its built-in fallback writes the rationale, with no external API call.
    """
    _imports()
    from schemas import CurriculumMatch, Evidence, TrendCluster, VerifiedTrend
    from agents.evaluation import EvaluationAgent
    from agents.recommendation import RecommendationAgent

    title = record["trend"]
    matching_signals = [signal for signal in signals if signal.title == title]
    trend = VerifiedTrend(
        cluster=TrendCluster(representative_title=title, signals=matching_signals),
        confidence=record["confidence"],
        verification_note=record["verification_note"],
        evidence=[Evidence(**item) for item in record.get("evidence", [])],
    )
    match_data = record.get("match")
    match = CurriculumMatch(**{key: value for key, value in match_data.items() if key != "citation"}) if match_data else None
    offline = _OfflineClient()
    evaluation = EvaluationAgent(client=offline).run(trend, match)
    # This is the same curriculum-search gate used by demo_snapshot.capture.
    curriculum_checked = trend.confidence >= 0.4
    recommendation = RecommendationAgent(client=offline).run(
        evaluation, curriculum_checked=curriculum_checked
    )
    return evaluation, recommendation
