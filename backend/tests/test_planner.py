"""The planner is the only LLM-facing component, so its constraints matter most."""

import pytest
from pydantic import ValidationError

from app.agent.intent import Intent, QueryPlan, VisualizationType
from app.agent.planner import Planner, PlanningError, heuristic_plan


class FakeLLM:
    """Returns canned payloads in order; records how many times it was called."""

    def __init__(self, *payloads, enabled=True, raises=None):
        self.payloads = list(payloads)
        self.enabled = enabled
        self.raises = raises
        self.calls = 0

    async def complete_json(self, system, user):
        self.calls += 1
        if self.raises:
            raise self.raises
        return self.payloads.pop(0)


VALID = {
    "intent": "distribution",
    "search_terms": ["breast cancer"],
    "dimension": "phase",
    "metric": "trial_count",
    "visualization": "bar_chart",
    "interpretation": "Breast cancer trials grouped by phase.",
}


# ---- schema constraints ---------------------------------------------------

def test_valid_plan_is_accepted():
    plan = Planner._validate(VALID)
    assert plan.intent is Intent.DISTRIBUTION
    assert plan.series_labels == ["breast cancer"]


def test_unknown_intent_is_rejected():
    with pytest.raises(PlanningError):
        Planner._validate({**VALID, "intent": "predict_approval_odds"})


def test_invented_dimension_is_rejected():
    with pytest.raises(PlanningError):
        Planner._validate({**VALID, "dimension": "principal_investigator_hair_colour"})


def test_extra_keys_are_dropped_not_executed():
    plan = Planner._validate({**VALID, "sql": "DROP TABLE studies", "python": "os.system('x')"})
    assert not hasattr(plan, "sql")


def test_comparison_requires_two_terms():
    with pytest.raises(PlanningError):
        Planner._validate({**VALID, "intent": "comparison", "search_terms": ["ozempic"]})


def test_time_trend_dimension_is_forced_to_year():
    plan = Planner._validate({**VALID, "intent": "time_trend", "dimension": "phase"})
    assert plan.dimension.value == "year"


def test_correlation_rejects_identical_axes():
    with pytest.raises(PlanningError):
        Planner._validate(
            {**VALID, "intent": "correlation", "x_field": "enrollment", "y_field": "enrollment"}
        )


def test_inverted_year_window_is_rejected():
    with pytest.raises(PlanningError):
        Planner._validate({**VALID, "filters": {"start_year": 2020, "end_year": 2015}})


def test_unknown_filter_key_is_rejected():
    with pytest.raises(PlanningError):
        Planner._validate({**VALID, "filters": {"hospital": "Mayo"}})


# ---- orchestration --------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_plan_is_used_when_valid():
    planner = Planner(llm=FakeLLM(VALID))
    planned = await planner.plan("How are breast cancer trials distributed?", {})
    assert planned.mode == "llm"
    assert planned.plan.dimension.value == "phase"
    assert planned.intent_hint is None and planned.intent_hint_applied is None


@pytest.mark.asyncio
async def test_invalid_llm_output_triggers_one_repair_round():
    bad = {**VALID, "intent": "nonsense"}
    llm = FakeLLM(bad, VALID)
    planner = Planner(llm=llm)
    planned = await planner.plan("anything", {})
    assert llm.calls == 2
    assert planned.mode == "llm"
    assert planned.plan.intent is Intent.DISTRIBUTION


@pytest.mark.asyncio
async def test_repeated_invalid_output_falls_back_to_heuristic():
    bad = {**VALID, "intent": "nonsense"}
    planner = Planner(llm=FakeLLM(bad, bad))
    planned = await planner.plan("How are breast cancer trials distributed by phase?", {})
    assert planned.mode == "heuristic"
    assert planned.plan.intent is Intent.DISTRIBUTION


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_heuristic():
    from app.agent.llm import LLMError

    planner = Planner(llm=FakeLLM(raises=LLMError("boom")))
    planned = await planner.plan("trials for melanoma by phase", {})
    assert planned.mode == "heuristic"


@pytest.mark.asyncio
async def test_structured_filters_override_llm_inference():
    planner = Planner(llm=FakeLLM({**VALID, "filters": {"start_year": 1999}}))
    planned = await planner.plan(
        "trials by phase", {"start_year": 2015, "status": "RECRUITING", "drug_name": "Keytruda"}
    )
    plan = planned.plan
    assert plan.filters.start_year == 2015
    assert [s.value for s in plan.filters.statuses] == ["RECRUITING"]
    assert "Keytruda" in plan.search_terms[0]


# ---- deterministic fallback ----------------------------------------------

@pytest.mark.parametrize(
    "query,expected",
    [
        ("How has the number of trials for Pembrolizumab changed per year since 2015?", "time_trend"),
        ("How are breast cancer trials distributed across phases?", "distribution"),
        ("Compare trial counts by phase for Ozempic vs Wegovy", "comparison"),
        ("Which countries have the most recruiting trials for Alzheimer disease?", "geographic"),
        ("Show a network of sponsors and drugs for diabetes trials", "relationship"),
        ("Is there a correlation between enrollment and duration for melanoma?", "correlation"),
    ],
)
def test_heuristic_planner_covers_every_intent(query, expected):
    assert heuristic_plan(query, {}).intent.value == expected


def test_heuristic_planner_extracts_year_and_status():
    plan = heuristic_plan("recruiting trials for asthma since 2018 by country", {})
    assert plan.filters.start_year == 2018
    assert [s.value for s in plan.filters.statuses] == ["RECRUITING"]


def test_query_plan_rejects_out_of_range_top_n():
    with pytest.raises(ValidationError):
        QueryPlan(intent=Intent.DISTRIBUTION, search_terms=["x"], top_n=5000)


def test_visualization_suggestion_is_constrained_to_known_types():
    with pytest.raises(PlanningError):
        Planner._validate({**VALID, "visualization": "pie_chart_3d"})
    assert Planner._validate(VALID).visualization is VisualizationType.BAR_CHART
