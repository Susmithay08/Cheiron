"""Deterministic visualization selection.

The LLM may *suggest* a chart type, but the backend decides. A suggestion is
honoured only if it appears in the allow-list for the resolved intent; otherwise
we fall back to the intent's default. This keeps a confused planner from
producing a spec the builders cannot actually fill.
"""

from __future__ import annotations

from app.agent.intent import Dimension, Intent, QueryPlan, VisualizationType

DEFAULT_BY_INTENT: dict[Intent, VisualizationType] = {
    Intent.TIME_TREND: VisualizationType.TIME_SERIES,
    Intent.DISTRIBUTION: VisualizationType.BAR_CHART,
    Intent.COMPARISON: VisualizationType.GROUPED_BAR_CHART,
    Intent.GEOGRAPHIC: VisualizationType.BAR_CHART,
    Intent.RELATIONSHIP: VisualizationType.NETWORK_GRAPH,
    Intent.CORRELATION: VisualizationType.SCATTER_PLOT,
}

ALLOWED_BY_INTENT: dict[Intent, set[VisualizationType]] = {
    Intent.TIME_TREND: {VisualizationType.TIME_SERIES, VisualizationType.BAR_CHART},
    Intent.DISTRIBUTION: {VisualizationType.BAR_CHART, VisualizationType.HISTOGRAM},
    Intent.COMPARISON: {VisualizationType.GROUPED_BAR_CHART, VisualizationType.BAR_CHART},
    Intent.GEOGRAPHIC: {VisualizationType.BAR_CHART},
    Intent.RELATIONSHIP: {VisualizationType.NETWORK_GRAPH},
    Intent.CORRELATION: {VisualizationType.SCATTER_PLOT},
}


def select_visualization(plan: QueryPlan) -> tuple[VisualizationType, list[str]]:
    """Return (chart type, notes explaining any override)."""
    notes: list[str] = []
    default = DEFAULT_BY_INTENT[plan.intent]
    suggestion = plan.visualization

    # A continuous dimension in a distribution is genuinely a histogram.
    if plan.intent == Intent.DISTRIBUTION and plan.dimension == Dimension.ENROLLMENT:
        return VisualizationType.HISTOGRAM, notes

    if suggestion is None:
        return default, notes

    if suggestion in ALLOWED_BY_INTENT[plan.intent]:
        return suggestion, notes

    notes.append(
        f"Planner suggested '{suggestion.value}', which is not valid for intent "
        f"'{plan.intent.value}'; used '{default.value}' instead."
    )
    return default, notes
