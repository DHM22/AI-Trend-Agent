"""Functions the agents can call to look up GitHub releases and search the curriculum.

The future implementations will consume and return the existing ``RawSignal``
and ``CurriculumMatch`` dataclasses from ``schemas.py``. This module will also
hold the JSON tool-schema definitions exposed to the agents.
"""

import sys
from pathlib import Path
from typing import Any

_SRC_DIR = str(Path(__file__).resolve().parents[1])
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from schemas import CurriculumMatch, RawSignal


def lookup_github(query: str, limit: int = 10) -> list[RawSignal]:
    """Look up GitHub evidence for a trend claim."""
    raise NotImplementedError


def search_curriculum(query: str, limit: int = 3) -> list[CurriculumMatch]:
    """Search indexed curriculum content for relevant slides."""
    raise NotImplementedError


def github_lookup_tool_schema() -> dict[str, Any]:
    """Return the JSON schema for the GitHub lookup tool."""
    raise NotImplementedError


def curriculum_search_tool_schema() -> dict[str, Any]:
    """Return the JSON schema for the curriculum search tool."""
    raise NotImplementedError
