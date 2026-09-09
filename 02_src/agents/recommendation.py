"""RecommendationAgent stub for orchestrating the trend-agent workflow.

The future implementation will coordinate ``VerifiedTrend``,
``CurriculumMatch``, and ``EvaluationResult`` values from ``schemas.py`` and
emit the final ``Recommendation`` with one of the five action tiers.
"""

import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1])
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from schemas import (
    CurriculumMatch,
    EvaluationResult,
    Recommendation,
    TrendCluster,
    VerifiedTrend,
)


class RecommendationAgent:
    """Orchestrate verification, curriculum, and evaluation agents."""

    def run(self, cluster: TrendCluster) -> Recommendation:
        """Return the final recommendation for one trend cluster."""
        raise NotImplementedError

    def recommend(
        self,
        trend: VerifiedTrend,
        match: CurriculumMatch | None,
        evaluation: EvaluationResult,
    ) -> Recommendation:
        """Assign an action tier and construct a recommendation."""
        raise NotImplementedError
