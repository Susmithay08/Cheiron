"""Public request/response schemas.

These are what `/docs` renders, so every field carries a description and the
models carry realistic examples.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.agent.intent import Intent, Phase, TrialStatus
from app.visualization.schemas import Visualization

MAX_QUERY_LENGTH = 500


class AnalyzeRequest(BaseModel):
    """A natural-language question plus optional structured narrowing filters.

    Structured fields are authoritative: whatever the planner infers from the
    prose, an explicitly supplied field always wins.
    """

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "How has the number of trials for this drug changed per year since 2015?",
                    "drug_name": "Pembrolizumab",
                    "start_year": 2015,
                }
            ]
        }
    }

    query: str = Field(
        min_length=3,
        max_length=MAX_QUERY_LENGTH,
        description="Natural-language question about clinical trials. Required.",
    )
    drug_name: Optional[str] = Field(
        default=None, max_length=120, description="Restrict the search to this intervention."
    )
    condition: Optional[str] = Field(
        default=None, max_length=120, description="Restrict the search to this condition/disease."
    )
    trial_phase: Optional[Phase] = Field(
        default=None, description="Keep only studies in this phase."
    )
    sponsor: Optional[str] = Field(
        default=None, max_length=200, description="Restrict to this lead sponsor."
    )
    country: Optional[str] = Field(
        default=None, max_length=100, description="Restrict to studies with a site in this country."
    )
    start_year: Optional[int] = Field(
        default=None, ge=1900, le=2100, description="Earliest study start year (inclusive)."
    )
    end_year: Optional[int] = Field(
        default=None, ge=1900, le=2100, description="Latest study start year (inclusive)."
    )
    status: Optional[TrialStatus] = Field(
        default=None, description="Keep only studies with this overall recruitment status."
    )
    intent_hint: Optional[Intent] = Field(
        default=None,
        description=(
            "Preferred analysis type, e.g. from a UI chip. A hint, never a command: the "
            "planner adopts it only when the question can actually support it, and the "
            "response reports whether it was applied. Omit to let the planner decide."
        ),
    )

    @field_validator("query")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query must not be blank")
        return cleaned

    def structured_filters(self) -> dict[str, Any]:
        """The structured *filter* fields only, as a plain dict.

        `intent_hint` is deliberately excluded: it steers interpretation rather
        than narrowing the search, and is passed to the planner separately.
        """
        return self.model_dump(
            exclude={"query", "intent_hint"}, exclude_none=True, mode="json"
        )


class PlanSummary(BaseModel):
    """The validated plan, surfaced so the interpretation is auditable."""

    intent: str
    search_terms: list[str]
    dimension: Optional[str] = None
    metric: str
    relationship: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    interpretation: str = ""
    planner_mode: str = Field(description="'llm' or 'heuristic' (deterministic fallback).")
    intent_hint: Optional[str] = Field(
        default=None, description="The intent hint supplied by the caller, if any."
    )
    intent_hint_applied: Optional[bool] = Field(
        default=None,
        description=(
            "True if the hint was adopted, False if the question could not support it "
            "and the planner's own intent was kept. Null when no hint was supplied."
        ),
    )


class ResponseMeta(BaseModel):
    request_id: str
    query: str
    source: str = "clinicaltrials.gov"
    source_api: str = "https://clinicaltrials.gov/api/v2"
    elapsed_ms: int
    plan: PlanSummary


class AnalyzeResponse(BaseModel):
    visualization: Visualization
    meta: ResponseMeta


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable explanation, safe to show a user.")
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": {
                        "code": "NO_MATCHING_TRIALS",
                        "message": "No ClinicalTrials.gov studies matched the supplied query and filters.",
                        "details": {"search_terms": ["zzzz"]},
                        "request_id": "b1f2...",
                    }
                }
            ]
        }
    }
    error: ErrorBody


class ExampleQuery(BaseModel):
    label: str
    query: str
    intent: str
