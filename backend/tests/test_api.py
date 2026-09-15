"""End-to-end HTTP tests with ClinicalTrials.gov and the LLM both mocked."""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.agent.planner import Planner
from app.main import app
from tests.conftest import study

BASE = "https://clinicaltrials.gov/api/v2"


class StubLLM:
    """Stands in for the planner's LLM so tests never leave the machine."""

    def __init__(self, payload=None, error=None):
        self.enabled = True
        self.payload = payload
        self.error = error

    async def complete_json(self, system, user):
        if self.error:
            raise self.error
        return self.payload


DISTRIBUTION_PLAN = {
    "intent": "distribution",
    "search_terms": ["melanoma"],
    "dimension": "phase",
    "metric": "trial_count",
    "visualization": "bar_chart",
    "interpretation": "Melanoma trials grouped by phase.",
}

CORPUS = {
    "studies": [
        study("NCT00000001", phases=["PHASE3"], title="Phase 3 melanoma study",
              interventions=[("Pembrolizumab", "DRUG")], countries=["United States"]),
        study("NCT00000002", phases=["PHASE3"], title="Another phase 3 study",
              interventions=[("Pembrolizumab", "DRUG")], countries=["Canada"]),
        study("NCT00000003", phases=["PHASE1"], title="Phase 1 study",
              interventions=[("Nivolumab", "DRUG")], countries=["France"]),
    ]
}


@pytest.fixture
def client(monkeypatch):
    """A TestClient whose planner uses a stub LLM by default."""
    with TestClient(app) as test_client:
        test_client.app.state.planner = Planner(llm=StubLLM(DISTRIBUTION_PLAN))
        yield test_client


# ---- happy path -----------------------------------------------------------

@respx.mock
def test_successful_request_returns_a_renderable_spec(client):
    respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(200, json=CORPUS))

    response = client.post("/analyze", json={"query": "How are melanoma trials split by phase?"})
    assert response.status_code == 200
    body = response.json()

    viz = body["visualization"]
    assert viz["type"] == "bar_chart"
    assert viz["title"]
    assert viz["encoding"]["x"]["field"] == "phase"
    assert viz["encoding"]["y"]["field"] == "trial_count"
    # Every encoded field exists on every row: the renderer contract.
    for row in viz["data"]:
        assert "phase" in row and "trial_count" in row
    assert {r["phase"]: r["trial_count"] for r in viz["data"]} == {"Phase 1": 1, "Phase 3": 2}

    assert viz["metadata"]["source"] == "ClinicalTrials.gov"
    assert viz["metadata"]["studies_matched"] == 3
    assert body["meta"]["plan"]["intent"] == "distribution"
    assert body["meta"]["plan"]["planner_mode"] == "llm"
    assert body["meta"]["request_id"]


@respx.mock
def test_citations_reference_only_retrieved_studies(client):
    respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(200, json=CORPUS))
    body = client.post("/analyze", json={"query": "melanoma by phase"}).json()

    retrieved = {"NCT00000001", "NCT00000002", "NCT00000003"}
    for row in body["visualization"]["data"]:
        assert row["citations"]
        for citation in row["citations"]:
            assert citation["nct_id"] in retrieved
            assert citation["excerpt"]
            assert citation["url"].startswith("https://clinicaltrials.gov/study/")


# ---- failure paths --------------------------------------------------------

@respx.mock
def test_empty_result_set_returns_a_structured_error(client):
    respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(200, json={"studies": []}))
    response = client.post("/analyze", json={"query": "trials for zzzzzz"})
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NO_MATCHING_TRIALS"
    assert error["details"]["search_terms"] == ["melanoma"]
    assert "visualization" not in response.json()


@respx.mock
def test_clinicaltrials_outage_is_reported_as_bad_gateway(client):
    respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(503))
    response = client.post("/analyze", json={"query": "melanoma by phase"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "CTGOV_UNAVAILABLE"


@respx.mock
def test_llm_failure_falls_back_to_the_deterministic_planner(client):
    from app.agent.llm import LLMError

    client.app.state.planner = Planner(llm=StubLLM(error=LLMError("provider down")))
    respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(200, json=CORPUS))

    response = client.post("/analyze", json={"query": "How are melanoma trials split by phase?"})
    assert response.status_code == 200
    assert response.json()["meta"]["plan"]["planner_mode"] == "heuristic"


@respx.mock
def test_field_with_no_coverage_is_an_explicit_error_not_an_empty_chart(client):
    client.app.state.planner = Planner(
        llm=StubLLM({**DISTRIBUTION_PLAN, "intent": "correlation", "dimension": None,
                     "x_field": "enrollment", "y_field": "duration_days"})
    )
    bare = {"studies": [study("NCT00000009", enrollment=None, start=None, completion=None)]}
    respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(200, json=bare))

    response = client.post("/analyze", json={"query": "enrollment vs duration"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_FIELD_COVERAGE"


@pytest.mark.parametrize(
    "payload",
    [
        {},                                  # missing query
        {"query": "  "},                     # blank query
        {"query": "hi"},                     # below min length
        {"query": "x" * 501},                # above max length
        {"query": "ok query", "start_year": 1600},        # year out of range
        {"query": "ok query", "status": "DEFINITELY_NOT"},  # invalid enum
    ],
)
def test_malformed_requests_are_rejected_with_field_details(client, payload):
    response = client.post("/analyze", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert response.json()["error"]["details"]["fields"]


# ---- supporting endpoints -------------------------------------------------

def test_health_reports_configuration_without_leaking_secrets(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "llm_api_key" not in str(body).lower()


def test_examples_cover_every_intent(client):
    intents = {e["intent"] for e in client.get("/examples").json()}
    assert intents == {
        "time_trend", "distribution", "comparison",
        "geographic", "relationship", "correlation",
    }


def test_openapi_documents_the_analyze_contract(client):
    schema = client.get("/openapi.json").json()
    assert "/analyze" in schema["paths"]
    assert "AnalyzeResponse" in schema["components"]["schemas"]
    assert "ErrorResponse" in schema["components"]["schemas"]
