"""Deep citations: link each visualized datum back to real trial records.

Strategy (documented in the README):

* Every aggregate carries the full list of NCT IDs that produced it, so the
  provenance is complete even when the rendered citation list is capped.
* We attach at most `MAX_CITATIONS_PER_DATUM` full citations per datum, chosen
  deterministically (first by NCT ID order) so responses are reproducible and
  bounded. `supporting_trial_count` and `supporting_nct_ids` report the rest.
* Each citation names the exact CT.gov field and the exact value read from it,
  plus the study title as a human-readable excerpt. Nothing is paraphrased.
"""

from __future__ import annotations

from typing import Iterable, Optional

from app.agent.intent import Dimension, NumericField
from app.clinicaltrials.models import Trial
from app.visualization.schemas import Citation

STUDY_URL = "https://clinicaltrials.gov/study/{nct_id}"

# Which CT.gov field each dimension reads, and how to render its value.
DIMENSION_SOURCE: dict[Dimension, tuple[str, str]] = {
    Dimension.YEAR: ("protocolSection.statusModule.startDateStruct.date", "start_date_raw"),
    Dimension.PHASE: ("protocolSection.designModule.phases", "primary_phase"),
    Dimension.STATUS: ("protocolSection.statusModule.overallStatus", "overall_status"),
    Dimension.STUDY_TYPE: ("protocolSection.designModule.studyType", "study_type"),
    Dimension.INTERVENTION_TYPE: (
        "protocolSection.armsInterventionsModule.interventions[].type",
        "_interventions",
    ),
    Dimension.COUNTRY: (
        "protocolSection.contactsLocationsModule.locations[].country",
        "_countries",
    ),
    Dimension.SPONSOR: (
        "protocolSection.sponsorCollaboratorsModule.leadSponsor.name",
        "lead_sponsor",
    ),
    Dimension.SPONSOR_CLASS: (
        "protocolSection.sponsorCollaboratorsModule.leadSponsor.class",
        "lead_sponsor_class",
    ),
    Dimension.CONDITION: ("protocolSection.conditionsModule.conditions", "_conditions"),
    Dimension.ENROLLMENT: (
        "protocolSection.designModule.enrollmentInfo.count",
        "enrollment",
    ),
}

NUMERIC_SOURCE: dict[NumericField, str] = {
    NumericField.ENROLLMENT: "protocolSection.designModule.enrollmentInfo.count",
    NumericField.START_YEAR: "protocolSection.statusModule.startDateStruct.date",
    NumericField.DURATION_DAYS: (
        "protocolSection.statusModule.startDateStruct.date + primaryCompletionDateStruct.date"
    ),
}


class CitationTracer:
    """Builds citations from an index of the trials that were actually fetched."""

    def __init__(self, trials: Iterable[Trial], max_per_datum: int = 5):
        self.index: dict[str, Trial] = {t.nct_id: t for t in trials}
        self.max_per_datum = max(1, max_per_datum)

    # ---- value rendering -------------------------------------------------
    @staticmethod
    def _value_for(trial: Trial, accessor: str, datum_key: str) -> str:
        """Render the exact supporting value, scoped to this datum where relevant."""
        if accessor == "_countries":
            return datum_key if datum_key in trial.countries else ", ".join(trial.countries[:3])
        if accessor == "_conditions":
            return datum_key if datum_key in trial.conditions else ", ".join(trial.conditions[:3])
        if accessor == "_interventions":
            matching = [i.name for i in trial.interventions if i.type == datum_key.upper().replace(" ", "_")]
            if matching:
                return f"{datum_key}: {', '.join(matching[:3])}"
            return ", ".join(sorted({i.type for i in trial.interventions}))
        value = getattr(trial, accessor, None)
        return "" if value is None else str(value)

    def _citation(self, nct_id: str, field_path: str, value: str) -> Optional[Citation]:
        trial = self.index.get(nct_id)
        if trial is None:
            return None  # never cite a trial we did not actually retrieve
        return Citation(
            nct_id=nct_id,
            field=field_path,
            value=value,
            excerpt=(trial.brief_title or trial.official_title or "")[:300],
            url=STUDY_URL.format(nct_id=nct_id),
        )

    # ---- public API ------------------------------------------------------
    def for_dimension(
        self, nct_ids: list[str], dimension: Dimension, datum_key: str
    ) -> tuple[list[Citation], list[str]]:
        """Citations for one categorical/time bucket, plus the full NCT ID list."""
        field_path, accessor = DIMENSION_SOURCE[dimension]
        ordered = sorted(nct_ids)
        citations = []
        for nct_id in ordered[: self.max_per_datum]:
            trial = self.index.get(nct_id)
            if trial is None:
                continue
            citation = self._citation(
                nct_id, field_path, self._value_for(trial, accessor, datum_key)
            )
            if citation:
                citations.append(citation)
        return citations, ordered

    def for_numeric_bucket(
        self, nct_ids: list[str], numeric_field: NumericField
    ) -> tuple[list[Citation], list[str]]:
        """Citations for a histogram bin."""
        field_path = NUMERIC_SOURCE[numeric_field]
        accessor = {
            NumericField.ENROLLMENT: "enrollment",
            NumericField.START_YEAR: "start_date_raw",
            NumericField.DURATION_DAYS: "duration_days",
        }[numeric_field]
        ordered = sorted(nct_ids)
        citations = []
        for nct_id in ordered[: self.max_per_datum]:
            trial = self.index.get(nct_id)
            if trial is None:
                continue
            citation = self._citation(nct_id, field_path, str(getattr(trial, accessor, "")))
            if citation:
                citations.append(citation)
        return citations, ordered

    def for_point(self, nct_id: str, x_field: NumericField, y_field: NumericField) -> list[Citation]:
        """A scatter point is one trial, so it cites both of its own values."""
        trial = self.index.get(nct_id)
        if trial is None:
            return []
        out = []
        for numeric_field in (x_field, y_field):
            accessor = {
                NumericField.ENROLLMENT: "enrollment",
                NumericField.START_YEAR: "start_date_raw",
                NumericField.DURATION_DAYS: "duration_days",
            }[numeric_field]
            citation = self._citation(
                nct_id, NUMERIC_SOURCE[numeric_field], str(getattr(trial, accessor, ""))
            )
            if citation:
                out.append(citation)
        return out

    def for_edge(self, nct_ids: list[str], source: str, target: str) -> tuple[list[Citation], list[str]]:
        """Citations for a network edge: the trials where both entities co-occur."""
        ordered = sorted(nct_ids)
        citations = []
        for nct_id in ordered[: self.max_per_datum]:
            trial = self.index.get(nct_id)
            if trial is None:
                continue
            citation = self._citation(
                nct_id,
                "protocolSection.sponsorCollaboratorsModule/armsInterventionsModule/conditionsModule",
                f"{source} ↔ {target}",
            )
            if citation:
                citations.append(citation)
        return citations, ordered
