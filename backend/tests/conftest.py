"""Shared fixtures. No test in this suite touches the live network."""

from __future__ import annotations

import pytest

from app.clinicaltrials.models import Trial


def study(
    nct_id: str,
    *,
    title: str = "A study",
    phases: list[str] | None = None,
    status: str = "RECRUITING",
    study_type: str = "INTERVENTIONAL",
    conditions: list[str] | None = None,
    interventions: list[tuple[str, str]] | None = None,
    sponsor: str = "Acme Pharma",
    sponsor_class: str = "INDUSTRY",
    start: str | None = "2021-03-10",
    completion: str | None = "2023-03-10",
    enrollment: int | None = 120,
    countries: list[str] | None = None,
) -> dict:
    """Build a raw CT.gov-shaped study payload for tests."""
    proto: dict = {
        "identificationModule": {"nctId": nct_id, "briefTitle": title},
        "statusModule": {"overallStatus": status},
        "designModule": {"studyType": study_type},
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": sponsor, "class": sponsor_class}
        },
    }
    if phases:
        proto["designModule"]["phases"] = phases
    if enrollment is not None:
        proto["designModule"]["enrollmentInfo"] = {"count": enrollment}
    if start:
        proto["statusModule"]["startDateStruct"] = {"date": start}
    if completion:
        proto["statusModule"]["primaryCompletionDateStruct"] = {"date": completion}
    if conditions:
        proto["conditionsModule"] = {"conditions": conditions}
    if interventions:
        proto["armsInterventionsModule"] = {
            "interventions": [{"name": n, "type": t} for n, t in interventions]
        }
    if countries:
        proto["contactsLocationsModule"] = {"locations": [{"country": c} for c in countries]}
    return {"protocolSection": proto}


@pytest.fixture
def trials() -> list[Trial]:
    """A small, deliberately messy corpus: missing phases, dates and enrollment."""
    raw = [
        study("NCT00000001", phases=["PHASE3"], start="2020-01-15",
              interventions=[("Pembrolizumab", "DRUG"), ("Placebo", "DRUG")],
              conditions=["Melanoma"], sponsor="Merck", countries=["United States", "Canada"]),
        study("NCT00000002", phases=["PHASE3"], start="2021-06-01",
              interventions=[("Pembrolizumab", "DRUG"), ("Chemotherapy", "DRUG")],
              conditions=["Melanoma"], sponsor="Merck", countries=["United States"]),
        study("NCT00000003", phases=["PHASE1", "PHASE2"], start="2021-02-01",
              interventions=[("Nivolumab", "DRUG")], conditions=["Lung Cancer"],
              sponsor="BMS", countries=["France"], enrollment=None),
        # No phase, no start date, no locations: must not crash anything.
        study("NCT00000004", phases=None, start=None, completion=None,
              interventions=None, conditions=None, sponsor="", countries=None,
              enrollment=45),
        study("NCT00000005", phases=["PHASE2"], start="2023-11-20", status="COMPLETED",
              interventions=[("Nivolumab", "DRUG"), ("Ipilimumab", "DRUG")],
              conditions=["Melanoma"], sponsor="BMS", countries=["United States", "Japan"]),
    ]
    return [t for t in (Trial.from_api(s) for s in raw) if t is not None]
