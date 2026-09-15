"""Turn aggregates + citations into the visualization contract.

One builder per chart type. Builders are pure: aggregates in, spec out. They
never fetch, never call an LLM, and never invent a value.
"""

from __future__ import annotations

from typing import Optional

from app.agent.intent import Dimension, Metric, NumericField, QueryPlan
from app.citations.tracer import CitationTracer
from app.execution.aggregations import Bucket, Edge, Node, Point
from app.visualization.schemas import (
    Encoding,
    EncodingChannel,
    Sort,
    Visualization,
    VisualizationMetadata,
)

DIMENSION_TITLES: dict[Dimension, str] = {
    Dimension.YEAR: "Start Year",
    Dimension.PHASE: "Phase",
    Dimension.STATUS: "Overall Status",
    Dimension.STUDY_TYPE: "Study Type",
    Dimension.INTERVENTION_TYPE: "Intervention Type",
    Dimension.COUNTRY: "Country",
    Dimension.SPONSOR: "Lead Sponsor",
    Dimension.SPONSOR_CLASS: "Sponsor Category",
    Dimension.CONDITION: "Condition",
    Dimension.ENROLLMENT: "Enrollment",
}

METRIC_TITLES: dict[Metric, tuple[str, str]] = {
    Metric.TRIAL_COUNT: ("Number of Trials", "trials"),
    Metric.ENROLLMENT_SUM: ("Total Enrollment", "participants"),
    Metric.ENROLLMENT_MEDIAN: ("Median Enrollment", "participants"),
}

NUMERIC_TITLES: dict[NumericField, tuple[str, str]] = {
    NumericField.ENROLLMENT: ("Enrollment", "participants"),
    NumericField.START_YEAR: ("Start Year", "year"),
    NumericField.DURATION_DAYS: ("Study Duration", "days"),
}

# The `data` row key that holds the quantitative value, per metric.
VALUE_FIELD = {
    Metric.TRIAL_COUNT: "trial_count",
    Metric.ENROLLMENT_SUM: "enrollment_sum",
    Metric.ENROLLMENT_MEDIAN: "enrollment_median",
}


def _number(value: float) -> float | int:
    """Counts are integers; keep medians/averages as floats."""
    return int(value) if float(value).is_integer() else round(value, 4)


def _citation_payload(
    tracer: CitationTracer, nct_ids: list[str], dimension: Dimension, datum_key: str
) -> dict:
    citations, all_ids = tracer.for_dimension(nct_ids, dimension, datum_key)
    return {
        "citations": [c.model_dump() for c in citations],
        "supporting_trial_count": len(all_ids),
        "supporting_nct_ids": all_ids[:200],
    }


def build_categorical(
    buckets: list[Bucket],
    plan: QueryPlan,
    tracer: CitationTracer,
    metadata: VisualizationMetadata,
    *,
    chart_type: str,
    title: str,
    description: str = "",
    grouped: bool = False,
) -> Visualization:
    """bar_chart / grouped_bar_chart / time_series all share this shape."""
    dimension = plan.dimension or Dimension.PHASE
    dim_key = dimension.value
    value_key = VALUE_FIELD[plan.metric]
    metric_title, unit = METRIC_TITLES[plan.metric]

    rows = []
    for bucket in buckets:
        row = {dim_key: bucket.label, value_key: _number(bucket.value)}
        if grouped and bucket.series:
            row["series"] = bucket.series
        row.update(_citation_payload(tracer, bucket.nct_ids, dimension, bucket.key))
        rows.append(row)

    temporal = dimension == Dimension.YEAR
    encoding = Encoding(
        x=EncodingChannel(
            field=dim_key,
            type="temporal" if temporal else "nominal",
            title=DIMENSION_TITLES[dimension],
        ),
        y=EncodingChannel(field=value_key, type="quantitative", title=metric_title),
        series=EncodingChannel(field="series", type="nominal", title="Series")
        if grouped
        else None,
    )

    metadata.metric = value_key
    metadata.unit = unit
    metadata.grouping = dim_key
    metadata.time_granularity = "year" if temporal else None
    metadata.sort = (
        Sort(field=dim_key, direction="asc")
        if temporal or dimension in (Dimension.PHASE, Dimension.STATUS)
        else Sort(field=value_key, direction="desc")
    )

    return Visualization(
        type=chart_type,
        title=title,
        description=description,
        encoding=encoding,
        data=rows,
        metadata=metadata,
    )


def build_histogram(
    buckets: list[Bucket],
    plan: QueryPlan,
    tracer: CitationTracer,
    metadata: VisualizationMetadata,
    numeric_field: NumericField,
    title: str,
    description: str = "",
) -> Visualization:
    axis_title, _ = NUMERIC_TITLES[numeric_field]
    rows = []
    for bucket in buckets:
        citations, all_ids = tracer.for_numeric_bucket(bucket.nct_ids, numeric_field)
        rows.append(
            {
                "bin": bucket.label,
                "trial_count": _number(bucket.value),
                "citations": [c.model_dump() for c in citations],
                "supporting_trial_count": len(all_ids),
                "supporting_nct_ids": all_ids[:200],
            }
        )

    metadata.metric = "trial_count"
    metadata.unit = "trials"
    metadata.grouping = numeric_field.value
    metadata.sort = Sort(field="bin", direction="asc")

    return Visualization(
        type="histogram",
        title=title,
        description=description,
        encoding=Encoding(
            x=EncodingChannel(field="bin", type="ordinal", title=f"{axis_title} (binned)"),
            y=EncodingChannel(field="trial_count", type="quantitative", title="Number of Trials"),
        ),
        data=rows,
        metadata=metadata,
    )


def build_scatter(
    points: list[Point],
    plan: QueryPlan,
    tracer: CitationTracer,
    metadata: VisualizationMetadata,
    title: str,
    description: str = "",
) -> Visualization:
    x_field = plan.x_field or NumericField.START_YEAR
    y_field = plan.y_field or NumericField.ENROLLMENT
    x_title, _ = NUMERIC_TITLES[x_field]
    y_title, y_unit = NUMERIC_TITLES[y_field]

    rows = [
        {
            x_field.value: _number(point.x),
            y_field.value: _number(point.y),
            "nct_id": point.nct_id,
            "label": point.label,
            "phase": point.group,
            "citations": [c.model_dump() for c in tracer.for_point(point.nct_id, x_field, y_field)],
            "supporting_trial_count": 1,
            "supporting_nct_ids": [point.nct_id],
        }
        for point in points
    ]

    metadata.metric = y_field.value
    metadata.unit = y_unit
    metadata.grouping = None
    metadata.sort = None

    return Visualization(
        type="scatter_plot",
        title=title,
        description=description,
        encoding=Encoding(
            x=EncodingChannel(field=x_field.value, type="quantitative", title=x_title),
            y=EncodingChannel(field=y_field.value, type="quantitative", title=y_title),
            color=EncodingChannel(field="phase", type="nominal", title="Phase"),
        ),
        data=rows,
        metadata=metadata,
    )


def build_network(
    nodes: list[Node],
    edges: list[Edge],
    tracer: CitationTracer,
    metadata: VisualizationMetadata,
    title: str,
    description: str = "",
) -> Visualization:
    node_rows = [
        {
            "id": n.id,
            "label": n.label,
            "group": n.group,
            "degree": n.degree,
            "trial_count": n.trial_count,
        }
        for n in nodes
    ]
    edge_rows = []
    for edge in edges:
        citations, all_ids = tracer.for_edge(edge.nct_ids, edge.source, edge.target)
        edge_rows.append(
            {
                "source": edge.source,
                "target": edge.target,
                "weight": edge.weight,
                "citations": [c.model_dump() for c in citations],
                "supporting_trial_count": len(all_ids),
                "supporting_nct_ids": all_ids[:200],
            }
        )

    metadata.metric = "weight"
    metadata.unit = "co-occurring trials"
    metadata.grouping = "entity_pair"
    metadata.sort = Sort(field="weight", direction="desc")

    return Visualization(
        type="network_graph",
        title=title,
        description=description,
        encoding=Encoding(
            node_id="id",
            node_label="label",
            node_group="group",
            edge_source="source",
            edge_target="target",
            edge_weight="weight",
        ),
        data=[],
        nodes=node_rows,
        edges=edge_rows,
        metadata=metadata,
    )


def title_for(plan: QueryPlan, series_label: Optional[str] = None) -> str:
    """Human-readable chart title derived from the plan (no LLM prose)."""
    metric_title, _ = METRIC_TITLES[plan.metric]
    subject = series_label or " vs ".join(plan.series_labels) or "Clinical Trials"
    subject = subject.title() if subject.islower() else subject

    if plan.intent.value == "relationship":
        kind = (plan.relationship.value if plan.relationship else "entity").replace("_", " ↔ ")
        return f"{kind.title()} Network for {subject} Trials"
    if plan.intent.value == "correlation":
        x_title, _ = NUMERIC_TITLES[plan.x_field or NumericField.START_YEAR]
        y_title, _ = NUMERIC_TITLES[plan.y_field or NumericField.ENROLLMENT]
        return f"{y_title} vs {x_title} for {subject} Trials"
    if plan.dimension == Dimension.YEAR:
        return f"{subject} Trials per Start Year"
    dimension_title = DIMENSION_TITLES[plan.dimension] if plan.dimension else "Category"
    return f"{subject} Trials by {dimension_title} ({metric_title})"
