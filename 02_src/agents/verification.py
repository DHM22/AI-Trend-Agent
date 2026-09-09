"""VerificationAgent stub for checking whether trend claims are real.

The future implementation will consume a ``TrendCluster`` and return a
``VerifiedTrend`` from ``schemas.py``. It will decide when the evidence is
sufficient to stop looking.
"""

import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1])
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from schemas import TrendCluster, VerifiedTrend


class VerificationAgent:
    """Decide whether a trend's claims are supported by sufficient evidence."""

    def run(self, cluster: TrendCluster) -> VerifiedTrend:
        """Verify one trend cluster and return its verification result."""
        raise NotImplementedError
