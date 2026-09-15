"""Optional integration tests against the real ClinicalTrials.gov API.

Deselected by default (`pytest -m "not live"`), because a green unit suite must
not depend on a third-party service being up. Run them with:

    pytest -m live
"""

import pytest

from app.clinicaltrials.client import ClinicalTrialsClient
from app.clinicaltrials.models import Trial
from app.config import Settings

pytestmark = pytest.mark.live


def settings() -> Settings:
    return Settings(llm_api_key="", ctgov_page_size=50, ctgov_max_studies=50,
                    ctgov_cache_ttl_seconds=0)


async def test_live_search_returns_normalizable_studies():
    async with ClinicalTrialsClient(settings()) as client:
        raw = await client.search_studies(
            query_term="pembrolizumab",
            fields=["NCTId", "BriefTitle", "Phase", "StartDate", "LeadSponsorName"],
        )
    assert raw, "ClinicalTrials.gov returned no studies for a very common drug"
    trials = [t for t in (Trial.from_api(s) for s in raw) if t is not None]
    assert len(trials) == len(raw), "every live study should normalize"
    assert all(t.nct_id.startswith("NCT") for t in trials)


async def test_live_status_filter_is_honoured():
    async with ClinicalTrialsClient(settings()) as client:
        raw = await client.search_studies(
            query_term="diabetes", statuses=["RECRUITING"],
            fields=["NCTId", "OverallStatus"],
        )
    trials = [Trial.from_api(s) for s in raw]
    assert all(t.overall_status == "RECRUITING" for t in trials if t)
