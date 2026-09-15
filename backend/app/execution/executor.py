"""Execution engine: validated plan -> real data -> visualization spec.

This is the deterministic half of the agent. It receives a `QueryPlan` that has
already been validated against the controlled vocabulary and performs every
factual step itself: retrieval, normalization, filtering, aggregation, chart
construction and citation tracing.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from app.agent.intent import Dimension, Intent, NumericField, QueryPlan
from app.citations.tracer import CitationTracer
from app.clinicaltrials.client import ClinicalTrialsClient, CTGovError
from app.clinicaltrials.field_mapping import fields_for_plan
from app.clinicaltrials.models import Trial
from app.config import Settings, get_settings
from app.execution import aggregations as agg
from app.logging_utils import log_event
from app.visualization import builders
from app.visualization.router import select_visualization
from app.visualization.schemas import Visualization, VisualizationMetadata


class ExecutionError(RuntimeError):
    def __init__(self, message: str, *, code: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class Executor:
    def __init__(self, client: ClinicalTrialsClient, settings: Optional[Settings] = None):
        self.client = client
        self.settings = settings or get_settings()
        # NCT IDs actually retrieved during the last execute(); the output
        # validator checks every citation against this set.
        self.retrieved_nct_ids: set[str] = set()

    # ---- retrieval -------------------------------------------------------
    async def _fetch_series(self, plan: QueryPlan, term: Optional[str]) -> list[Trial]:
        """Fetch and normalize one search arm."""
        raw = await self.client.search_studies(
            query_term=term or None,
            sponsor=plan.filters.sponsor,
            location=plan.filters.country,
            statuses=[s.value for s in plan.filters.statuses] or None,
            phases=[p.value for p in plan.filters.phases] or None,
            study_type=plan.filters.study_type,
            fields=fields_for_plan(plan),
        )
        trials = [t for t in (Trial.from_api(study) for study in raw) if t is not None]
        log_event("normalized", term=term, raw=len(raw), normalized=len(trials))
        return trials

    def _apply_client_filters(self, trials: list[Trial], plan: QueryPlan) -> list[Trial]:
        """Year windows are not expressible as a CT.gov filter, so apply them here."""
        start, end = plan.filters.start_year, plan.filters.end_year
        if not start and not end:
            return trials
        kept = []
        for trial in trials:
            year = trial.start_year
            if year is None:
                continue  # a year filter cannot be satisfied by an undated trial
            if start and year < start:
                continue
            if end and year > end:
                continue
            kept.append(trial)
        return kept

    # ---- orchestration ---------------------------------------------------
    async def execute(self, plan: QueryPlan) -> Visualization:
        terms = plan.search_terms or [None]
        try:
            results = await asyncio.gather(*(self._fetch_series(plan, t) for t in terms))
        except CTGovError as exc:
            raise ExecutionError(str(exc), code=exc.code) from exc

        retrieved = sum(len(r) for r in results)
        series_trials = [self._apply_client_filters(r, plan) for r in results]
        matched = sum(len(r) for r in series_trials)
        log_event("retrieval_complete", retrieved=retrieved, matched=matched)

        if matched == 0:
            raise ExecutionError(
                "No ClinicalTrials.gov studies matched the supplied query and filters.",
                code="NO_MATCHING_TRIALS",
                details={
                    "search_terms": plan.search_terms,
                    "filters": plan.filters.model_dump(exclude_none=True),
                    "studies_retrieved_before_filters": retrieved,
                },
            )

        all_trials = [t for series in series_trials for t in series]
        self.retrieved_nct_ids = {t.nct_id for t in all_trials}
        tracer = CitationTracer(all_trials, self.settings.max_citations_per_datum)
        chart_type, notes = select_visualization(plan)

        metadata = VisualizationMetadata(
            metric=plan.metric.value,
            filters_applied=plan.filters.model_dump(exclude_none=True, exclude_defaults=True),
            search_terms=plan.search_terms,
            studies_retrieved=retrieved,
            studies_matched=matched,
            truncated=retrieved >= self.settings.ctgov_max_studies,
            assumptions=list(plan.assumptions),
            notes=notes,
        )
        if metadata.truncated:
            metadata.notes.append(
                f"Result set was capped at {self.settings.ctgov_max_studies} studies per search "
                "term; counts reflect that sample, not the full registry."
            )

        builder = {
            Intent.TIME_TREND: self._build_time_series,
            Intent.DISTRIBUTION: self._build_distribution,
            Intent.COMPARISON: self._build_comparison,
            Intent.GEOGRAPHIC: self._build_distribution,
            Intent.RELATIONSHIP: self._build_network,
            Intent.CORRELATION: self._build_scatter,
        }[plan.intent]

        visualization = builder(plan, series_trials, tracer, metadata, chart_type)
        log_event(
            "visualization_built",
            type=visualization.type,
            data_points=len(visualization.data),
            nodes=len(visualization.nodes or []),
            edges=len(visualization.edges or []),
        )
        return visualization

    # ---- per-intent builders --------------------------------------------
    def _build_time_series(self, plan, series_trials, tracer, metadata, chart_type) -> Visualization:
        multi = len(series_trials) > 1
        buckets: list[agg.Bucket] = []
        for label, trials in zip(plan.series_labels or [None], series_trials):
            series_buckets = agg.aggregate_by_dimension(
                trials, Dimension.YEAR, plan.metric, series=label if multi else None
            )
            buckets.extend(agg.fill_year_gaps(series_buckets, label if multi else None))
        return builders.build_categorical(
            buckets,
            plan,
            tracer,
            metadata,
            chart_type=chart_type,
            title=builders.title_for(plan),
            description=(
                "Number of studies whose ClinicalTrials.gov start date falls in each year. "
                "Years with no studies are shown explicitly as zero."
            ),
            grouped=multi,
        )

    def _build_distribution(self, plan, series_trials, tracer, metadata, chart_type) -> Visualization:
        trials = [t for series in series_trials for t in series]
        dimension = plan.dimension or Dimension.PHASE

        if chart_type == "histogram":
            numeric_field = NumericField.ENROLLMENT
            buckets = agg.build_histogram(trials, numeric_field)
            if not buckets:
                raise ExecutionError(
                    "Matching studies do not report enrollment, so no histogram can be built.",
                    code="INSUFFICIENT_FIELD_COVERAGE",
                    details={"field": numeric_field.value, "studies_matched": len(trials)},
                )
            return builders.build_histogram(
                buckets, plan, tracer, metadata, numeric_field,
                title=builders.title_for(plan),
                description=(
                    "Distribution of reported enrollment across matching studies. Bins span up "
                    "to the Tukey upper fence; larger studies are collected in the final "
                    "overflow bin so outliers do not flatten the shape."
                ),
            )

        buckets = agg.aggregate_by_dimension(trials, dimension, plan.metric, top_n=plan.top_n)
        if not buckets:
            raise ExecutionError(
                f"Matching studies do not report '{dimension.value}', so the chart would be empty.",
                code="INSUFFICIENT_FIELD_COVERAGE",
                details={"dimension": dimension.value, "studies_matched": len(trials)},
            )
        note = (
            f"Showing the top {len(buckets)} of {dimension.value} values by {plan.metric.value}."
            if len(buckets) >= plan.top_n
            else ""
        )
        if note:
            metadata.notes.append(note)
        description = (
            "A multinational study is counted once per country in which it has a listed site, "
            "so country counts sum to more than the number of studies."
            if dimension == Dimension.COUNTRY
            else f"Studies grouped by {dimension.value.replace('_', ' ')}."
        )
        return builders.build_categorical(
            buckets, plan, tracer, metadata,
            chart_type=chart_type, title=builders.title_for(plan), description=description,
        )

    def _build_comparison(self, plan, series_trials, tracer, metadata, chart_type) -> Visualization:
        dimension = plan.dimension or Dimension.PHASE
        buckets: list[agg.Bucket] = []
        for label, trials in zip(plan.series_labels, series_trials):
            buckets.extend(
                agg.aggregate_by_dimension(
                    trials, dimension, plan.metric, series=label, top_n=plan.top_n
                )
            )
        if not buckets:
            raise ExecutionError(
                f"Matching studies do not report '{dimension.value}'.",
                code="INSUFFICIENT_FIELD_COVERAGE",
                details={"dimension": dimension.value},
            )
        per_series = {
            label: len(trials) for label, trials in zip(plan.series_labels, series_trials)
        }
        metadata.notes.append(
            "Studies matched per series: "
            + ", ".join(f"{k}={v}" for k, v in per_series.items())
        )
        return builders.build_categorical(
            buckets, plan, tracer, metadata,
            chart_type=chart_type,
            title=builders.title_for(plan),
            description=(
                "Each series is an independent ClinicalTrials.gov search; a study mentioning "
                "both terms is counted in both series."
            ),
            grouped=True,
        )

    def _build_network(self, plan, series_trials, tracer, metadata, chart_type) -> Visualization:
        trials = [t for series in series_trials for t in series]
        nodes, edges = agg.build_network(trials, plan.relationship, top_n=plan.top_n)
        if not edges:
            raise ExecutionError(
                "Matching studies do not contain enough linked entities to form a network.",
                code="INSUFFICIENT_RELATIONSHIPS",
                details={
                    "relationship": plan.relationship.value if plan.relationship else None,
                    "studies_matched": len(trials),
                },
            )
        metadata.notes.append(
            f"Network pruned to the {plan.top_n} most connected entities per group and the "
            f"{len(edges)} strongest edges; edge weight is the number of studies in which the "
            "two entities co-occur."
        )
        return builders.build_network(
            nodes, edges, tracer, metadata,
            title=builders.title_for(plan),
            description="Nodes are entities; an edge means the pair appears together in a study.",
        )

    def _build_scatter(self, plan, series_trials, tracer, metadata, chart_type) -> Visualization:
        trials = [t for series in series_trials for t in series]
        points = agg.build_scatter(trials, plan.x_field, plan.y_field)
        if not points:
            raise ExecutionError(
                "No matching study reports both requested numeric fields.",
                code="INSUFFICIENT_FIELD_COVERAGE",
                details={
                    "x_field": plan.x_field.value,
                    "y_field": plan.y_field.value,
                    "studies_matched": len(trials),
                },
            )
        if len(points) >= agg.SCATTER_POINT_LIMIT:
            metadata.notes.append(
                f"Plotted the first {agg.SCATTER_POINT_LIMIT} of {len(trials)} matching studies "
                "that report both fields; the scatter is a sample, not the full set."
            )
        else:
            metadata.notes.append(
                f"{len(points)} of {len(trials)} matching studies report both fields; studies "
                "missing either value are omitted rather than imputed."
            )
        return builders.build_scatter(
            points, plan, tracer, metadata,
            title=builders.title_for(plan),
            description="One point per study; studies missing either value are excluded.",
        )
