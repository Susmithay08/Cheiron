"""Aggregation is the only place chart numbers are produced, so it is tested
directly against a known corpus rather than through the HTTP layer."""

from app.agent.intent import Dimension, Metric, NumericField, RelationshipKind
from app.execution import aggregations as agg


def _by_label(buckets):
    return {b.label: b.value for b in buckets}


def test_phase_counts_and_order(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.PHASE)
    assert _by_label(buckets) == {
        "Phase 3": 2.0,
        "Phase 2": 2.0,  # NCT...003 (Phase1/2 -> highest) and NCT...005
        "Not Applicable": 1.0,
    }
    # Ordinal dimensions keep clinical order, not value order.
    assert [b.label for b in buckets] == ["Phase 2", "Phase 3", "Not Applicable"]


def test_year_counts_and_gap_filling(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.YEAR)
    assert _by_label(buckets) == {"2020": 1.0, "2021": 2.0, "2023": 1.0}
    filled = agg.fill_year_gaps(buckets)
    assert [b.key for b in filled] == ["2020", "2021", "2022", "2023"]
    assert _by_label(filled)["2022"] == 0.0


def test_country_counts_a_trial_once_per_country(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.COUNTRY)
    counts = _by_label(buckets)
    assert counts["United States"] == 3.0
    assert counts["Canada"] == 1.0
    # Sorted by value descending for unordered dimensions.
    assert buckets[0].label == "United States"


def test_top_n_truncates_unordered_dimensions(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.COUNTRY, top_n=2)
    assert len(buckets) == 2


def test_enrollment_metrics_ignore_missing_values(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.PHASE, Metric.ENROLLMENT_SUM)
    # Phase 2 = NCT...003 (enrollment None, skipped) + NCT...005 (120)
    assert _by_label(buckets)["Phase 2"] == 120.0


def test_buckets_carry_every_contributing_nct_id(trials):
    buckets = agg.aggregate_by_dimension(trials, Dimension.PHASE)
    phase3 = next(b for b in buckets if b.label == "Phase 3")
    assert sorted(phase3.nct_ids) == ["NCT00000001", "NCT00000002"]
    assert phase3.value == len(phase3.nct_ids)


def test_network_edges_weight_by_co_occurring_trials(trials):
    nodes, edges = agg.build_network(trials, RelationshipKind.SPONSOR_DRUG)
    weights = {(e.source, e.target): e.weight for e in edges}
    assert weights[("Merck", "Pembrolizumab")] == 2
    assert weights[("BMS", "Nivolumab")] == 2
    # Placebo is a real intervention but a meaningless network node.
    assert not any("Placebo" in (e.source, e.target) for e in edges)
    # Every edge endpoint has a node.
    node_ids = {n.id for n in nodes}
    assert all(e.source in node_ids and e.target in node_ids for e in edges)


def test_drug_drug_network_pairs_co_occurring_drugs(trials):
    _, edges = agg.build_network(trials, RelationshipKind.DRUG_DRUG)
    pairs = {(e.source, e.target) for e in edges}
    assert ("Ipilimumab", "Nivolumab") in pairs


def test_network_is_empty_when_no_entities_link(trials):
    isolated = [t for t in trials if t.nct_id == "NCT00000004"]
    assert agg.build_network(isolated, RelationshipKind.SPONSOR_DRUG) == ([], [])


def test_scatter_drops_trials_missing_either_value(trials):
    points = agg.build_scatter(trials, NumericField.START_YEAR, NumericField.ENROLLMENT)
    ids = {p.nct_id for p in points}
    assert "NCT00000003" not in ids  # enrollment missing
    assert "NCT00000004" not in ids  # start date missing
    assert len(points) == 3


def test_histogram_bins_are_contiguous_and_complete(trials):
    buckets = agg.build_histogram(trials, NumericField.ENROLLMENT, bins=4)
    assert sum(b.value for b in buckets) == 4  # four trials report enrollment
    assert all(b.nct_ids for b in buckets)


def test_histogram_of_identical_values_returns_single_bin(trials):
    same = [t for t in trials if t.enrollment == 120]
    buckets = agg.build_histogram(same, NumericField.ENROLLMENT)
    assert len(buckets) == 1
    assert buckets[0].value == len(same)


def test_histogram_without_values_is_empty(trials):
    no_enrollment = [t for t in trials if t.enrollment is None]
    assert agg.build_histogram(no_enrollment, NumericField.ENROLLMENT) == []


def test_histogram_isolates_outliers_in_an_overflow_bin():
    """One 70,000-participant study must not flatten every real trial into one bin."""
    from app.clinicaltrials.models import Trial
    from tests.conftest import study

    corpus = [
        Trial.from_api(study(f"NCT{i:08d}", enrollment=enrollment))
        for i, enrollment in enumerate([10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 70000])
    ]
    buckets = agg.build_histogram(corpus, NumericField.ENROLLMENT, bins=5)

    assert buckets[-1].label.startswith(">")
    assert buckets[-1].value == 1.0
    assert buckets[-1].nct_ids == ["NCT00000010"]
    # The remaining studies are spread across bins rather than piled into one.
    assert sum(b.value for b in buckets) == len(corpus)
    assert len([b for b in buckets[:-1] if b.value > 0]) >= 3
