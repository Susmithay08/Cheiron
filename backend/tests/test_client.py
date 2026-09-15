"""CT.gov client: pagination, retries, caching, error mapping. All mocked."""

import httpx
import pytest
import respx

from app.clinicaltrials.client import ClinicalTrialsClient, CTGovError
from app.config import Settings
from tests.conftest import study

BASE = "https://clinicaltrials.gov/api/v2"


def settings(**overrides) -> Settings:
    defaults = dict(
        ctgov_base_url=BASE, ctgov_page_size=2, ctgov_max_studies=10,
        ctgov_cache_ttl_seconds=0, llm_api_key="",
    )
    return Settings(**{**defaults, **overrides})


def page(ids, token=None):
    body = {"studies": [study(i) for i in ids]}
    if token:
        body["nextPageToken"] = token
    return httpx.Response(200, json=body)


@respx.mock
async def test_pagination_follows_every_page():
    route = respx.get(f"{BASE}/studies").mock(
        side_effect=[
            page(["NCT1", "NCT2"], token="t1"),
            page(["NCT3", "NCT4"], token="t2"),
            page(["NCT5"]),
        ]
    )
    async with ClinicalTrialsClient(settings()) as client:
        studies = await client.search_studies(query_term="melanoma")

    assert len(studies) == 5
    assert route.call_count == 3
    # The second and third requests must carry the page token.
    assert "pageToken=t1" in str(route.calls[1].request.url)


@respx.mock
async def test_pagination_stops_at_the_configured_cap():
    respx.get(f"{BASE}/studies").mock(
        side_effect=[page(["A", "B"], token=f"t{i}") for i in range(10)]
    )
    async with ClinicalTrialsClient(settings(ctgov_max_studies=4)) as client:
        studies = await client.search_studies(query_term="x")
    assert len(studies) == 4


@respx.mock
async def test_missing_next_page_token_ends_pagination():
    respx.get(f"{BASE}/studies").mock(return_value=page(["NCT1"]))
    async with ClinicalTrialsClient(settings()) as client:
        assert len(await client.search_studies(query_term="x")) == 1


@respx.mock
async def test_transient_server_error_is_retried():
    route = respx.get(f"{BASE}/studies").mock(
        side_effect=[httpx.Response(503), httpx.Response(500), page(["NCT1"])]
    )
    async with ClinicalTrialsClient(settings()) as client:
        studies = await client.search_studies(query_term="x")
    assert route.call_count == 3
    assert len(studies) == 1


@respx.mock
async def test_persistent_failure_raises_ctgov_error():
    respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(503))
    async with ClinicalTrialsClient(settings()) as client:
        with pytest.raises(CTGovError):
            await client.search_studies(query_term="x")


@respx.mock
async def test_bad_request_is_not_retried():
    route = respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(400, text="bad filter"))
    async with ClinicalTrialsClient(settings()) as client:
        with pytest.raises(CTGovError) as exc:
            await client.search_studies(query_term="x")
    assert exc.value.code == "CTGOV_BAD_QUERY"
    assert route.call_count == 1


@respx.mock
async def test_malformed_payload_is_rejected():
    respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(200, json={"studies": "nope"}))
    async with ClinicalTrialsClient(settings()) as client:
        with pytest.raises(CTGovError):
            await client.search_studies(query_term="x")


@respx.mock
async def test_identical_requests_hit_the_cache():
    route = respx.get(f"{BASE}/studies").mock(return_value=page(["NCT1"]))
    async with ClinicalTrialsClient(settings(ctgov_cache_ttl_seconds=60)) as client:
        await client.search_studies(query_term="same")
        await client.search_studies(query_term="same")
        await client.search_studies(query_term="different")
    assert route.call_count == 2


@respx.mock
async def test_filters_are_pushed_down_to_the_api():
    route = respx.get(f"{BASE}/studies").mock(return_value=page(["NCT1"]))
    async with ClinicalTrialsClient(settings()) as client:
        await client.search_studies(
            query_term="melanoma",
            statuses=["RECRUITING"],
            phases=["PHASE2", "PHASE3"],
            study_type="INTERVENTIONAL",
            fields=["NCTId", "Phase"],
        )
    url = str(route.calls[0].request.url)
    assert "filter.overallStatus=RECRUITING" in url
    assert "PHASE2+OR+PHASE3" in url.replace("%20", "+")
    assert "fields=NCTId%2CPhase" in url
