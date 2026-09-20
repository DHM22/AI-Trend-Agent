"""Nullable report contracts, independent of the agent pipeline."""

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Action = Literal["update_existing_material", "add_optional_content", "add_new_lesson", "watch"]
UnitInterval = Annotated[float, Field(ge=0, le=1)]
Count = Annotated[int, Field(ge=0)]


class ReportModel(BaseModel):
    # Preserve extra snapshot metadata in the validated JSON endpoint.
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class Evidence(ReportModel):
    source: Optional[str] = None
    tier: Optional[Literal["primary", "secondary"]] = None
    url: Optional[str] = None
    note: Optional[str] = None


class CurriculumMatch(ReportModel):
    week: Optional[Count] = None
    topic: Optional[str] = None
    source_file: Optional[str] = None
    slide_number: Optional[Count] = None
    matched_text: Optional[str] = None
    similarity: Optional[UnitInterval] = None
    exact_match: Optional[str] = None
    content_type: Optional[Literal["lab", "slides"]] = None
    citation: Optional[str] = None


class Recommendation(ReportModel):
    trend: Optional[str] = None
    confidence: Optional[UnitInterval] = None
    total_score: Optional[Annotated[float, Field(ge=0, le=5)]] = None
    verification_note: Optional[str] = None
    recommended_action: Optional[Action] = None
    action_plan: Optional[list[str]] = Field(default_factory=list)
    evidence: Optional[list[Evidence]] = Field(default_factory=list)
    match: Optional[CurriculumMatch] = None


class Report(ReportModel):
    captured_at: Optional[datetime] = None
    source_signals: Optional[str] = None
    signals_in_file: Optional[Count] = None
    clusters_total: Optional[Count] = None
    clusters_processed: Optional[Count] = None
    duplicates_collapsed: Optional[Count] = None
    tier_counts: Optional[dict[str, Optional[Count]]] = Field(default_factory=dict)
    recommendations: Optional[list[Recommendation]] = Field(default_factory=list)
