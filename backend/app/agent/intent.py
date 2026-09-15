"""The controlled vocabulary the planner is allowed to emit.

Everything the LLM produces is constrained to these enums. Anything else is
rejected by Pydantic before a single API call is made.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Intent(str, Enum):
    TIME_TREND = "time_trend"
    DISTRIBUTION = "distribution"
    COMPARISON = "comparison"
    GEOGRAPHIC = "geographic"
    RELATIONSHIP = "relationship"
    CORRELATION = "correlation"


class Dimension(str, Enum):
    """A field trials can be grouped by."""

    YEAR = "year"
    PHASE = "phase"
    STATUS = "status"
    STUDY_TYPE = "study_type"
    INTERVENTION_TYPE = "intervention_type"
    COUNTRY = "country"
    SPONSOR = "sponsor"
    SPONSOR_CLASS = "sponsor_class"
    CONDITION = "condition"
    ENROLLMENT = "enrollment"


class Metric(str, Enum):
    TRIAL_COUNT = "trial_count"
    ENROLLMENT_SUM = "enrollment_sum"
    ENROLLMENT_MEDIAN = "enrollment_median"


class RelationshipKind(str, Enum):
    SPONSOR_DRUG = "sponsor_drug"
    DRUG_DRUG = "drug_drug"
    CONDITION_INTERVENTION = "condition_intervention"
    SPONSOR_CONDITION = "sponsor_condition"


class NumericField(str, Enum):
    ENROLLMENT = "enrollment"
    START_YEAR = "start_year"
    DURATION_DAYS = "duration_days"


class VisualizationType(str, Enum):
    BAR_CHART = "bar_chart"
    GROUPED_BAR_CHART = "grouped_bar_chart"
    TIME_SERIES = "time_series"
    SCATTER_PLOT = "scatter_plot"
    HISTOGRAM = "histogram"
    NETWORK_GRAPH = "network_graph"


class TrialStatus(str, Enum):
    RECRUITING = "RECRUITING"
    NOT_YET_RECRUITING = "NOT_YET_RECRUITING"
    ACTIVE_NOT_RECRUITING = "ACTIVE_NOT_RECRUITING"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"
    WITHDRAWN = "WITHDRAWN"
    SUSPENDED = "SUSPENDED"
    ENROLLING_BY_INVITATION = "ENROLLING_BY_INVITATION"
    UNKNOWN = "UNKNOWN"


class Phase(str, Enum):
    EARLY_PHASE1 = "EARLY_PHASE1"
    PHASE1 = "PHASE1"
    PHASE2 = "PHASE2"
    PHASE3 = "PHASE3"
    PHASE4 = "PHASE4"
    NA = "NA"


class PlanFilters(BaseModel):
    """Filters pushed down to the ClinicalTrials.gov query where possible."""

    model_config = {"extra": "forbid"}

    statuses: list[TrialStatus] = Field(
        default_factory=list, description="Overall recruitment statuses to keep."
    )
    phases: list[Phase] = Field(default_factory=list, description="Trial phases to keep.")
    study_type: Optional[Literal["INTERVENTIONAL", "OBSERVATIONAL", "EXPANDED_ACCESS"]] = None
    country: Optional[str] = Field(default=None, max_length=100)
    sponsor: Optional[str] = Field(default=None, max_length=200)
    start_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    end_year: Optional[int] = Field(default=None, ge=1900, le=2100)

    @model_validator(mode="after")
    def _years_ordered(self):
        if self.start_year and self.end_year and self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")
        return self


class QueryPlan(BaseModel):
    """The structured execution plan. This is the ONLY thing the LLM produces."""

    model_config = {"extra": "forbid"}

    intent: Intent
    search_terms: list[str] = Field(
        default_factory=list,
        max_length=6,
        description=(
            "Free-text terms sent to CT.gov query.term. For a comparison, one entry "
            "per compared arm (e.g. ['Ozempic', 'Wegovy'])."
        ),
    )
    series_labels: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="Human-readable label for each search term, same order.",
    )
    filters: PlanFilters = Field(default_factory=PlanFilters)
    dimension: Optional[Dimension] = Field(
        default=None, description="Field to group by (not used for correlation/relationship)."
    )
    metric: Metric = Metric.TRIAL_COUNT
    relationship: Optional[RelationshipKind] = None
    x_field: Optional[NumericField] = None
    y_field: Optional[NumericField] = None
    visualization: Optional[VisualizationType] = Field(
        default=None, description="LLM suggestion; the backend router has final say."
    )
    top_n: int = Field(default=15, ge=3, le=50)
    interpretation: str = Field(
        default="", max_length=400, description="One-sentence restatement of the question."
    )
    assumptions: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("search_terms", "series_labels", mode="before")
    @classmethod
    def _clean_terms(cls, v):
        if isinstance(v, list):
            return [str(t).strip() for t in v if str(t).strip()][:6]
        return v

    @model_validator(mode="after")
    def _intent_requirements(self):
        """Each intent needs a coherent shape; repair what is safely repairable."""
        if self.intent == Intent.TIME_TREND:
            self.dimension = Dimension.YEAR
        elif self.intent == Intent.GEOGRAPHIC:
            self.dimension = Dimension.COUNTRY
        elif self.intent == Intent.RELATIONSHIP:
            self.relationship = self.relationship or RelationshipKind.SPONSOR_DRUG
            self.dimension = None
        elif self.intent == Intent.CORRELATION:
            self.x_field = self.x_field or NumericField.START_YEAR
            self.y_field = self.y_field or NumericField.ENROLLMENT
            if self.x_field == self.y_field:
                raise ValueError("correlation requires two distinct numeric fields")
            self.dimension = None
        elif self.intent in (Intent.DISTRIBUTION, Intent.COMPARISON):
            self.dimension = self.dimension or Dimension.PHASE

        if self.intent == Intent.COMPARISON and len(self.search_terms) < 2:
            raise ValueError("comparison intent requires at least two search terms")

        # Labels default to the terms themselves.
        if len(self.series_labels) != len(self.search_terms):
            self.series_labels = list(self.search_terms)
        return self
