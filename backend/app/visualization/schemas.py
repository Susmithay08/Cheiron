"""The visualization contract returned to the frontend.

One generic envelope for every chart type. A renderer only needs to switch on
`visualization.type` and read `encoding` to know which field of each `data` row
maps to which visual channel — it never needs backend-specific knowledge.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A pointer from a visualized datum back into one ClinicalTrials.gov study."""

    nct_id: str = Field(description="ClinicalTrials.gov registry identifier.")
    field: str = Field(description="Which CT.gov field supports the datum, e.g. 'startDate'.")
    value: str = Field(description="The exact field value read from the API response.")
    excerpt: str = Field(description="Short human-readable supporting text (usually the title).")
    url: str = Field(description="Deep link to the study record.")


class EncodingChannel(BaseModel):
    """One visual channel bound to a field of every `data` row."""

    field: str = Field(description="Key present on every object in `data`.")
    type: Literal["nominal", "ordinal", "quantitative", "temporal"] = Field(
        description="Scale type the frontend should use for this channel."
    )
    title: Optional[str] = Field(default=None, description="Axis/legend label.")


class Encoding(BaseModel):
    """Channel map. Cartesian charts use x/y/series; network graphs use nodes/edges."""

    x: Optional[EncodingChannel] = None
    y: Optional[EncodingChannel] = None
    series: Optional[EncodingChannel] = Field(
        default=None, description="Field that splits data into colored series."
    )
    color: Optional[EncodingChannel] = None
    # Network-only channels.
    node_id: Optional[str] = Field(default=None, description="Key of the node identifier.")
    node_label: Optional[str] = None
    node_group: Optional[str] = Field(default=None, description="Key used to colour nodes.")
    edge_source: Optional[str] = None
    edge_target: Optional[str] = None
    edge_weight: Optional[str] = None


class Sort(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "desc"


class VisualizationMetadata(BaseModel):
    """Everything a renderer needs beyond the raw data points."""

    source: str = "ClinicalTrials.gov"
    source_api: str = "https://clinicaltrials.gov/api/v2/studies"
    metric: str = Field(description="What the quantitative channel measures.")
    unit: str = Field(default="trials", description="Unit of the quantitative channel.")
    sort: Optional[Sort] = None
    time_granularity: Optional[Literal["year"]] = None
    grouping: Optional[str] = Field(default=None, description="Dimension trials were grouped by.")
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    search_terms: list[str] = Field(default_factory=list)
    studies_retrieved: int = 0
    studies_matched: int = 0
    truncated: bool = Field(
        default=False,
        description=(
            "True if more studies matched on ClinicalTrials.gov than were retrieved, so the "
            "chart describes a capped sample rather than the full result set."
        ),
    )
    studies_available: Optional[int] = Field(
        default=None,
        description=(
            "Total matching studies reported by ClinicalTrials.gov (`totalCount`), summed "
            "across search arms. None when the registry did not report it."
        ),
    )
    assumptions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Visualization(BaseModel):
    """The visualization specification itself."""

    type: Literal[
        "bar_chart",
        "grouped_bar_chart",
        "time_series",
        "scatter_plot",
        "histogram",
        "network_graph",
    ]
    title: str
    description: str = ""
    encoding: Encoding
    data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Cartesian charts: one row per datum. Network graphs: empty (see `nodes`/`edges`).",
    )
    nodes: Optional[list[dict[str, Any]]] = None
    edges: Optional[list[dict[str, Any]]] = None
    metadata: VisualizationMetadata
