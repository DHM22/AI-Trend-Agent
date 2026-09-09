"""EvaluationAgent stub for scoring trend maturity and curriculum relevance.

The future implementation will consume a ``VerifiedTrend`` and optional
``CurriculumMatch`` from ``schemas.py``, then return an ``EvaluationResult``
with a plain-language rationale.
"""

import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1])
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from schemas import CurriculumMatch, EvaluationResult, VerifiedTrend


class EvaluationAgent:
    """Score the maturity and relevance of a verified trend."""

    def run(
        self,
        trend: VerifiedTrend,
        match: CurriculumMatch | None,
    ) -> EvaluationResult:
        """Evaluate a trend and explain the resulting scores."""
        raise NotImplementedError
