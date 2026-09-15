"""Visualization routing, building, citation tracing and output validation."""

import pytest

from app.agent.intent import (
    Dimension,
    Intent,
    NumericField,
    QueryPlan,
    RelationshipKind,
    VisualizationType,
)
from app.citations.tracer import CitationTracer
from app.execution import aggregations as agg
from app.validation.validator import OutputValidationError, validate_visualization
from app.visualization import builders
from app.visualization.router import select_visualization
from app.visualization.schemas import VisualizationMetadata


def meta():
    return VisualizationMetadata(metric="trial_count")


def plan(**kwargs) -> QueryPlan:
    base = dict(intent=Intent.DISTRIBUTION, search_terms=["melanoma"], dimension=Dimension.PHASE)
    return QueryPlan(**{**base, **kwargs})


# ---- router ---------------------------------------------------------------

@pytest.mark.parametrize(
    "intent,expected",
    [
        (Intent.TIME_TREND, "time_series"),
        (Intent.DISTRIBUTION, "bar_chart"),
        (Intent.COMPARISON, "grouped_bar_chart"),
        (Intent.GEOGRAPHIC, "bar_chart"),
        (Intent.RELATIONSHIP, "network_graph"),
        (Intent.CORRELATION, "scatter_plot"),
    ],
)
def test_router_default_per_intent(intent, expected):
    terms = ["a", "b"] if intent is Intent.COMPARISON else ["a"]
    chart, notes = select_visualization(QueryPlan(intent=intent, search_terms=terms))
    assert chart.value == expected
    assert notes == []


def test_router_rejects_a_chart_type_the_intent_cannot_fill():
    chart, notes = select_visualization(
        QueryPlan(intent=Intent.RELATIONSHIP, search_terms=["a"],
                  visualization=VisualizationType.SCATTER_PLOT)
    )
    assert chart is VisualizationType.NETWORK_GRAPH
    assert notes and "not valid for intent" in notes[0]


def test_router_honours_a_legitimate_suggestion():
    chart, notes = select_visualization(
        QueryPlan(intent=Intent.TIME_TREND, search_terms=["a"],
                  visualization=VisualizationType.BAR_CHART)
    )
    assert chart is VisualizationType.BAR_CHART
    assert notes == []


def test_continuous_distribution_becomes_a_histogram():
    chart, _ = select_visualization(plan(dimension=Dimension.ENROLLMENT))
    assert chart is VisualizationType.HISTOGRAM


# ---- builders + citations -------------------------------------------------

def test_bar_chart_encoding_matches_its_data(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.PHASE)
    viz = builders.build_categorical(
        buckets, plan(), CitationTracer(trials), meta(),
        chart_type="bar_chart", title="Phases",
    )
    assert viz.encoding.x.field in viz.data[0]
    assert viz.encoding.y.field in viz.data[0]
    assert all(isinstance(row["trial_count"], int) for row in viz.data)
    validate_visualization(viz, {t.nct_id for t in trials})


def test_every_citation_points_at_a_retrieved_trial(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.PHASE)
    viz = builders.build_categorical(
        buckets, plan(), CitationTracer(trials), meta(), chart_type="bar_chart", title="t"
    )
    known = {t.nct_id for t in trials}
    for row in viz.data:
        assert row["citations"], "every datum must carry at least one citation"
        assert all(c["nct_id"] in known for c in row["citations"])
        assert row["supporting_trial_count"] == row["trial_count"]


def test_citation_value_is_the_actual_field_value(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.YEAR)
    viz = builders.build_categorical(
        buckets, plan(dimension=Dimension.YEAR, intent=Intent.TIME_TREND),
        CitationTracer(trials), meta(), chart_type="time_series", title="t",
    )
    row_2020 = next(r for r in viz.data if r["year"] == "2020")
    citation = row_2020["citations"][0]
    assert citation["value"].startswith("2020")
    assert citation["field"].endswith("startDateStruct.date")
    assert citation["url"].endswith(citation["nct_id"])


def test_citations_are_capped_but_provenance_is_complete(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.PHASE)
    viz = builders.build_categorical(
        buckets, plan(), CitationTracer(trials, max_per_datum=1), meta(),
        chart_type="bar_chart", title="t",
    )
    phase3 = next(r for r in viz.data if r["phase"] == "Phase 3")
    assert len(phase3["citations"]) == 1
    assert phase3["supporting_trial_count"] == 2
    assert len(phase3["supporting_nct_ids"]) == 2


def test_tracer_refuses_to_cite_an_unretrieved_trial(trials):
    tracer = CitationTracer(trials)
    citations, ids = tracer.for_dimension(["NCT99999999"], Dimension.PHASE, "Phase 3")
    assert citations == []
    assert ids == ["NCT99999999"]


def test_network_spec_is_well_formed(trials):
    nodes, edges = agg.build_network(trials, RelationshipKind.SPONSOR_DRUG)
    viz = builders.build_network(nodes, edges, CitationTracer(trials), meta(), title="net")
    assert viz.type == "network_graph"
    assert viz.data == []
    assert viz.encoding.node_id == "id"
    validate_visualization(viz, {t.nct_id for t in trials})


def test_scatter_points_cite_both_of_their_own_values(trials):
    points = agg.build_scatter(trials, NumericField.START_YEAR, NumericField.ENROLLMENT)
    viz = builders.build_scatter(
        points,
        plan(intent=Intent.CORRELATION, dimension=None,
             x_field=NumericField.START_YEAR, y_field=NumericField.ENROLLMENT),
        CitationTracer(trials), meta(), title="scatter",
    )
    row = viz.data[0]
    assert {c["nct_id"] for c in row["citations"]} == {row["nct_id"]}
    assert len(row["citations"]) == 2
    validate_visualization(viz, {t.nct_id for t in trials})


# ---- output validation ----------------------------------------------------

def test_validator_rejects_encoding_pointing_at_a_missing_field(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.PHASE)
    viz = builders.build_categorical(
        buckets, plan(), CitationTracer(trials), meta(), chart_type="bar_chart", title="t"
    )
    viz.encoding.x.field = "not_a_field"
    with pytest.raises(OutputValidationError, match="absent from data"):
        validate_visualization(viz, {t.nct_id for t in trials})


def test_validator_rejects_non_numeric_quantitative_values(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.PHASE)
    viz = builders.build_categorical(
        buckets, plan(), CitationTracer(trials), meta(), chart_type="bar_chart", title="t"
    )
    viz.data[0]["trial_count"] = "lots"
    with pytest.raises(OutputValidationError, match="non-numeric"):
        validate_visualization(viz, {t.nct_id for t in trials})


def test_validator_rejects_a_fabricated_citation(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.PHASE)
    viz = builders.build_categorical(
        buckets, plan(), CitationTracer(trials), meta(), chart_type="bar_chart", title="t"
    )
    viz.data[0]["citations"].append(
        {"nct_id": "NCT13371337", "field": "phase", "value": "Phase 3",
         "excerpt": "invented", "url": "https://example.com"}
    )
    with pytest.raises(OutputValidationError, match="not retrieved"):
        validate_visualization(viz, {t.nct_id for t in trials})


def test_validator_rejects_an_edge_with_no_matching_node(trials):
    nodes, edges = agg.build_network(trials, RelationshipKind.SPONSOR_DRUG)
    viz = builders.build_network(nodes, edges, CitationTracer(trials), meta(), title="net")
    viz.edges[0]["target"] = "Ghost Drug"
    with pytest.raises(OutputValidationError, match="no matching node"):
        validate_visualization(viz, {t.nct_id for t in trials})


def test_validator_rejects_an_empty_chart(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.PHASE)
    viz = builders.build_categorical(
        buckets, plan(), CitationTracer(trials), meta(), chart_type="bar_chart", title="t"
    )
    viz.data = []
    with pytest.raises(OutputValidationError, match="no data points"):
        validate_visualization(viz, set())
