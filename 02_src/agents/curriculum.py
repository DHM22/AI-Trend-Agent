"""CurriculumAgent stub for curriculum retrieval and relevance judgment.

The future implementation will consume a ``VerifiedTrend`` and return a
``CurriculumMatch`` from ``schemas.py`` after searching the vector store and
judging whether a retrieved slide is genuinely relevant.
"""

import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1])
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from schemas import CurriculumMatch, VerifiedTrend


class CurriculumAgent:
    """Find and judge the curriculum material related to a verified trend."""

    def run(self, trend: VerifiedTrend) -> CurriculumMatch | None:
        """Search the vector store and return a relevant curriculum match."""
        raise NotImplementedError
