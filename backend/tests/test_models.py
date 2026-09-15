"""Normalization must never crash on real-world sparse records."""

from datetime import date

from app.clinicaltrials.models import Trial
from tests.conftest import study


def test_missing_optional_fields_are_safe(trials):
    sparse = next(t for t in trials if t.nct_id == "NCT00000004")
    assert sparse.phases == []
    assert sparse.primary_phase == "Not Applicable"
    assert sparse.start_date is None
    assert sparse.start_year is None
    assert sparse.duration_days is None
    assert sparse.countries == []
    assert sparse.drug_names == []


def test_partial_dates_are_parsed():
    assert Trial.from_api(study("NCT1", start="2019")).start_date == date(2019, 1, 1)
    assert Trial.from_api(study("NCT2", start="2019-07")).start_date == date(2019, 7, 1)
    assert Trial.from_api(study("NCT3", start="not-a-date")).start_date is None


def test_study_without_nct_id_is_dropped():
    assert Trial.from_api({"protocolSection": {"identificationModule": {}}}) is None
    assert Trial.from_api({}) is None


def test_multi_phase_study_reports_highest_phase():
    trial = Trial.from_api(study("NCT4", phases=["PHASE1", "PHASE2"]))
    assert trial.primary_phase == "Phase 2"


def test_drug_names_exclude_non_drug_interventions():
    trial = Trial.from_api(
        study("NCT5", interventions=[("Drug A", "DRUG"), ("MRI", "DEVICE"), ("Vax", "BIOLOGICAL")])
    )
    assert trial.drug_names == ["Drug A", "Vax"]


def test_duration_days_is_none_when_completion_precedes_start():
    trial = Trial.from_api(study("NCT6", start="2022-01-01", completion="2021-01-01"))
    assert trial.duration_days is None
