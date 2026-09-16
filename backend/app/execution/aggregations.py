"""Deterministic aggregation over normalized trials.

Nothing in this module talks to an LLM. Every number that ends up in a chart is
computed here, in plain Python, from `Trial` objects that came out of the
ClinicalTrials.gov API. Each aggregate also carries the list of NCT IDs that
produced it, which is what the citation tracer later turns into deep citations.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from app.agent.intent import Dimension, Metric, NumericField, RelationshipKind
from app.clinicaltrials.models import (
    PHASE_LABELS,
    STATUS_LABELS,
    Trial,
    humanize,
)


@dataclass(slots=True)
class Bucket:
    """One aggregated category: a bar, a time point, a grouped-bar cell."""

    key: str
    label: str
    value: float
    series: Optional[str] = None
    nct_ids: list[str] = field(default_factory=list)
    sort_key: float | str = 0


@dataclass(slots=True)
class Edge:
    source: str
    target: str
    weight: int
    nct_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Node:
    id: str
    label: str
    group: str
    degree: int = 0
    trial_count: int = 0


@dataclass(slots=True)
class Point:
    """One scatter observation, traceable to exactly one trial."""

    x: float
    y: float
    nct_id: str
    label: str
    group: str = ""


# ---------------------------------------------------------------------------
# Dimension extractors: Trial -> zero or more (key, label) pairs
# ---------------------------------------------------------------------------

def _phase_keys(t: Trial) -> list[tuple[str, str]]:
    label = t.primary_phase
    return [(label, label)]


def _year_keys(t: Trial) -> list[tuple[str, str]]:
    year = t.start_year
    return [(str(year), str(year))] if year else []


def _country_keys(t: Trial) -> list[tuple[str, str]]:
    """A multinational trial counts once per country it runs in."""
    return [(c, c) for c in t.countries]


def _intervention_type_keys(t: Trial) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for i in t.interventions:
        label = humanize(i.type, {})
        seen[label] = label
    return list(seen.items())


def _condition_keys(t: Trial) -> list[tuple[str, str]]:
    return [(c, c) for c in dict.fromkeys(t.conditions)]


DIMENSION_EXTRACTORS: dict[Dimension, Callable[[Trial], list[tuple[str, str]]]] = {
    Dimension.YEAR: _year_keys,
    Dimension.PHASE: _phase_keys,
    Dimension.STATUS: lambda t: [(t.overall_status, humanize(t.overall_status, STATUS_LABELS))],
    Dimension.STUDY_TYPE: lambda t: [(t.study_type, humanize(t.study_type, {}))],
    Dimension.INTERVENTION_TYPE: _intervention_type_keys,
    Dimension.COUNTRY: _country_keys,
    Dimension.SPONSOR: lambda t: [(t.lead_sponsor, t.lead_sponsor)] if t.lead_sponsor else [],
    Dimension.SPONSOR_CLASS: lambda t: [
        (t.lead_sponsor_class, humanize(t.lead_sponsor_class, {}))
    ],
    Dimension.CONDITION: _condition_keys,
    Dimension.ENROLLMENT: lambda t: [(str(t.enrollment), str(t.enrollment))]
    if t.enrollment is not None
    else [],
}

# Categories that have a natural order and must NOT be sorted by value.
ORDERED_DIMENSIONS = {
    Dimension.PHASE: list(PHASE_LABELS.values()),
    Dimension.STATUS: list(STATUS_LABELS.values()),
}


def _metric_value(metric: Metric, trials: list[Trial]) -> float:
    if metric == Metric.TRIAL_COUNT:
        return float(len(trials))
    enrollments = [t.enrollment for t in trials if isinstance(t.enrollment, int)]
    if not enrollments:
        return 0.0
    if metric == Metric.ENROLLMENT_SUM:
        return float(sum(enrollments))
    return float(statistics.median(enrollments))


def aggregate_by_dimension(
    trials: Iterable[Trial],
    dimension: Dimension,
    metric: Metric = Metric.TRIAL_COUNT,
    *,
    series: Optional[str] = None,
    top_n: Optional[int] = None,
) -> list[Bucket]:
    """Group trials by `dimension` and reduce each group with `metric`."""
    extractor = DIMENSION_EXTRACTORS[dimension]
    groups: dict[str, list[Trial]] = defaultdict(list)
    labels: dict[str, str] = {}

    for trial in trials:
        for key, label in extractor(trial):
            if not key:
                continue
            groups[key].append(trial)
            labels[key] = label

    buckets = [
        Bucket(
            key=key,
            label=labels[key],
            value=_metric_value(metric, members),
            series=series,
            nct_ids=[t.nct_id for t in members],
        )
        for key, members in groups.items()
    ]

    if dimension == Dimension.YEAR:
        buckets.sort(key=lambda b: int(b.key))
        for b in buckets:
            b.sort_key = int(b.key)
        return buckets

    if dimension in ORDERED_DIMENSIONS:
        order = ORDERED_DIMENSIONS[dimension]
        buckets.sort(key=lambda b: (order.index(b.label) if b.label in order else len(order)))
        for i, b in enumerate(buckets):
            b.sort_key = i
        return buckets

    buckets.sort(key=lambda b: (-b.value, b.label))
    if top_n:
        buckets = buckets[:top_n]
    for i, b in enumerate(buckets):
        b.sort_key = i
    return buckets


def fill_year_gaps(buckets: list[Bucket], series: Optional[str] = None) -> list[Bucket]:
    """Insert explicit zeros for missing years so the line does not lie."""
    if not buckets:
        return buckets
    years = [int(b.key) for b in buckets]
    existing = {b.key: b for b in buckets}
    filled = []
    for year in range(min(years), max(years) + 1):
        key = str(year)
        filled.append(
            existing.get(key)
            or Bucket(key=key, label=key, value=0.0, series=series, nct_ids=[], sort_key=year)
        )
    return filled


# ---------------------------------------------------------------------------
# Networks
# ---------------------------------------------------------------------------

# Control arms are real interventions but carry no relational meaning: an edge
# "Sponsor X -- Placebo" says nothing about what the sponsor develops.
UNINFORMATIVE_DRUGS = {
    "placebo", "placebos", "saline", "normal saline", "matching placebo",
    "placebo comparator", "standard of care", "usual care", "control", "vehicle",
    "placebo oral tablet", "placebo oral capsule", "sham", "no intervention",
}


def _informative_drugs(trial: Trial) -> list[str]:
    return [d for d in dict.fromkeys(trial.drug_names) if d.lower() not in UNINFORMATIVE_DRUGS]


def _entity_pairs(trial: Trial, kind: RelationshipKind) -> list[tuple[tuple[str, str], tuple[str, str]]]:
    """Return ((source_id, source_group), (target_id, target_group)) pairs."""
    pairs = []
    if kind == RelationshipKind.SPONSOR_DRUG:
        if trial.lead_sponsor:
            for drug in _informative_drugs(trial):
                pairs.append(((trial.lead_sponsor, "sponsor"), (drug, "drug")))
    elif kind == RelationshipKind.DRUG_DRUG:
        drugs = sorted(_informative_drugs(trial))
        for i, a in enumerate(drugs):
            for b in drugs[i + 1 :]:
                pairs.append(((a, "drug"), (b, "drug")))
    elif kind == RelationshipKind.CONDITION_INTERVENTION:
        for condition in dict.fromkeys(trial.conditions):
            for drug in _informative_drugs(trial):
                pairs.append(((condition, "condition"), (drug, "drug")))
    elif kind == RelationshipKind.SPONSOR_CONDITION:
        if trial.lead_sponsor:
            for condition in dict.fromkeys(trial.conditions):
                pairs.append(((trial.lead_sponsor, "sponsor"), (condition, "condition")))
    return pairs


def build_network(
    trials: Iterable[Trial], kind: RelationshipKind, top_n: int = 15
) -> tuple[list[Node], list[Edge]]:
    """Build a co-occurrence network, pruned to the strongest edges.

    Pruning matters: an unpruned sponsor-drug graph for a common condition has
    thousands of degree-1 nodes and communicates nothing. We keep the `top_n`
    busiest entities on each side, then keep edges between survivors.
    """
    edge_trials: dict[tuple[str, str], list[str]] = defaultdict(list)
    node_meta: dict[str, str] = {}
    node_trials: dict[str, set[str]] = defaultdict(set)

    for trial in trials:
        for (src, src_group), (dst, dst_group) in _entity_pairs(trial, kind):
            src, dst = src.strip(), dst.strip()
            if not src or not dst or src == dst:
                continue
            node_meta[src] = src_group
            node_meta[dst] = dst_group
            node_trials[src].add(trial.nct_id)
            node_trials[dst].add(trial.nct_id)
            key = (src, dst)
            if trial.nct_id not in edge_trials[key]:
                edge_trials[key].append(trial.nct_id)

    if not edge_trials:
        return [], []

    # Keep the busiest entities per group so both sides stay represented.
    by_group: dict[str, list[str]] = defaultdict(list)
    for node_id, group in node_meta.items():
        by_group[group].append(node_id)
    keep: set[str] = set()
    for group, members in by_group.items():
        members.sort(key=lambda n: (-len(node_trials[n]), n))
        keep.update(members[:top_n])

    edges = [
        Edge(source=src, target=dst, weight=len(ncts), nct_ids=ncts)
        for (src, dst), ncts in edge_trials.items()
        if src in keep and dst in keep
    ]
    edges.sort(key=lambda e: (-e.weight, e.source, e.target))
    edges = edges[: top_n * 4]

    connected = {e.source for e in edges} | {e.target for e in edges}
    degrees: dict[str, int] = defaultdict(int)
    for e in edges:
        degrees[e.source] += 1
        degrees[e.target] += 1

    nodes = [
        Node(
            id=node_id,
            label=node_id,
            group=node_meta[node_id],
            degree=degrees[node_id],
            trial_count=len(node_trials[node_id]),
        )
        for node_id in sorted(connected, key=lambda n: (-degrees[n], n))
    ]
    return nodes, edges


# ---------------------------------------------------------------------------
# Scatter / histogram
# ---------------------------------------------------------------------------

_NUMERIC_ACCESSORS: dict[NumericField, Callable[[Trial], Optional[float]]] = {
    NumericField.ENROLLMENT: lambda t: float(t.enrollment) if t.enrollment is not None else None,
    NumericField.START_YEAR: lambda t: float(t.start_year) if t.start_year else None,
    NumericField.DURATION_DAYS: lambda t: float(t.duration_days)
    if t.duration_days is not None
    else None,
}


# A scatter with more points than this is unreadable and makes responses huge.
SCATTER_POINT_LIMIT = 500


def build_scatter(
    trials: Iterable[Trial],
    x_field: NumericField,
    y_field: NumericField,
    limit: int = SCATTER_POINT_LIMIT,
) -> list[Point]:
    """Keep only trials where BOTH numeric fields are present. No imputation."""
    get_x, get_y = _NUMERIC_ACCESSORS[x_field], _NUMERIC_ACCESSORS[y_field]
    points: list[Point] = []
    for trial in trials:
        x, y = get_x(trial), get_y(trial)
        if x is None or y is None:
            continue
        points.append(
            Point(x=x, y=y, nct_id=trial.nct_id, label=trial.brief_title, group=trial.primary_phase)
        )
        if len(points) >= limit:
            break
    return points


def build_histogram(trials: Iterable[Trial], field_name: NumericField, bins: int = 12) -> list[Bucket]:
    """Equal-width bins over a numeric field, robust to outliers.

    Trial enrollment is heavily right-skewed: one 70,000-participant screening
    study would otherwise squash every real trial into a single bin. So the bins
    span up to the Tukey upper fence (Q3 + 1.5 x IQR) and everything above goes
    into a labelled overflow bucket. The tail is disclosed, not discarded, and
    the rule behaves sensibly at any sample size.
    """
    accessor = _NUMERIC_ACCESSORS[field_name]
    valued = [(v, t) for v, t in ((accessor(t), t) for t in trials) if v is not None]
    if not valued:
        return []

    values = sorted(v for v, _ in valued)
    if values[0] == values[-1]:
        return [
            Bucket(
                key=f"{values[0]:g}",
                label=f"{values[0]:g}",
                value=float(len(valued)),
                nct_ids=[t.nct_id for _, t in valued],
                sort_key=0,
            )
        ]

    q1 = values[len(values) // 4]
    q3 = values[(3 * len(values)) // 4]
    low = values[0]
    fence = q3 + 1.5 * (q3 - q1)
    high = min(values[-1], fence) if fence > low else values[-1]
    if high <= low:
        high = values[-1]

    width = (high - low) / bins
    groups: dict[int, list[Trial]] = defaultdict(list)
    overflow: list[Trial] = []
    for value, trial in valued:
        if value > high:
            overflow.append(trial)
        else:
            groups[min(int((value - low) / width), bins - 1) if value > low else 0].append(trial)

    # Every bin is emitted, including empty ones: a histogram that silently drops
    # its gaps misrepresents the shape of the distribution.
    buckets = [
        Bucket(
            key=f"{low + i * width:.0f}-{low + (i + 1) * width:.0f}",
            label=f"{low + i * width:.0f}–{low + (i + 1) * width:.0f}",
            value=float(len(groups.get(i, []))),
            nct_ids=[t.nct_id for t in groups.get(i, [])],
            sort_key=i,
        )
        for i in range(bins)
    ]
    if overflow:
        buckets.append(
            Bucket(
                key=f">{high:.0f}",
                label=f">{high:.0f}",
                value=float(len(overflow)),
                nct_ids=[t.nct_id for t in overflow],
                sort_key=bins,
            )
        )
    return buckets
