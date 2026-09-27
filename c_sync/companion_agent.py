"""
C-Sync's window onto the Companion (the sixth agent).
=====================================================
The Companion itself -- its LLM tool loop and the only OpenAI client in the
project's UI story -- lives in 02_src/agents/companion.py, OUTSIDE C-Sync, so
C-Sync keeps its guarantee of running no agent and building no client.

This module re-exports only the Companion's PURE analysis functions (which need
no key, no network) plus a `make_companion` factory the page uses to open a chat
session. It deliberately names no `*Agent` symbol and imports nothing from
`openai`, so the C-Sync "no agent is run" invariant in test_chain.py still holds
for every file in this directory.
"""

from __future__ import annotations

import sys

# The pipeline lives in the backend checkout; ui_adapter already resolves where.
from ui_adapter import SRC

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.companion import (            # noqa: E402  (path set up just above)
    audit_run,
    curriculum_checked,
    curriculum_status,
    explain_decision,
    get_trend,
    make_companion,
    rank_trends,
    search_trends,
    snapshot_info,
    what_if,
    _match_object,
)

__all__ = [
    "audit_run", "curriculum_checked", "curriculum_status", "explain_decision",
    "get_trend", "make_companion", "rank_trends", "search_trends", "snapshot_info",
    "what_if", "_match_object",
]
