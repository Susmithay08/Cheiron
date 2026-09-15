"""Normalized trial model.

The CT.gov v2 payload is deeply nested and every field is optional in practice.
We flatten it once, here, so nothing downstream has to defend against missing
keys. Every accessor returns a safe default rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


def _get(obj: Any, *path: str, default: Any = None) -> Any:
    """Walk a nested dict path, tolerating missing or non-dict nodes."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def _parse_partial_date(raw: Optional[str]) -> Optional[date]:
    """CT.gov dates may be 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD'."""
    if not raw or not isinstance(raw, str):
        return None
    parts = raw.strip().split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


@dataclass(slots=True)
class Intervention:
    name: str
    type: str = "UNKNOWN"


@dataclass(slots=True)
class Trial:
    """Flat, always-safe view of one ClinicalTrials.gov study."""

    nct_id: str
    brief_title: str = ""
    official_title: str = ""
    overall_status: str = "UNKNOWN"
    study_type: str = "UNKNOWN"
    phases: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    interventions: list[Intervention] = field(default_factory=list)
    lead_sponsor: str = ""
    lead_sponsor_class: str = "UNKNOWN"
    collaborators: list[str] = field(default_factory=list)
    start_date: Optional[date] = None
    start_date_raw: str = ""
    completion_date: Optional[date] = None
    completion_date_raw: str = ""
    enrollment: Optional[int] = None
    countries: list[str] = field(default_factory=list)

    # ---- derived helpers -------------------------------------------------
    @property
    def start_year(self) -> Optional[int]:
        return self.start_date.year if self.start_date else None

    @property
    def duration_days(self) -> Optional[int]:
        if self.start_date and self.completion_date:
            delta = (self.completion_date - self.start_date).days
            return delta if delta >= 0 else None
        return None

    @property
    def primary_phase(self) -> str:
        """One display phase per trial; multi-phase studies take the highest."""
        if not self.phases:
            return "Not Applicable"
        order = ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4"]
        ranked = [p for p in order if p in self.phases]
        return PHASE_LABELS.get(ranked[-1] if ranked else self.phases[0],
                                self.phases[0].replace("_", " ").title())

    @property
    def drug_names(self) -> list[str]:
        """Interventions that are actually drugs/biologics, title-cased."""
        return [
            i.name.strip()
            for i in self.interventions
            if i.type in ("DRUG", "BIOLOGICAL") and i.name.strip()
        ]

    @classmethod
    def from_api(cls, study: dict) -> Optional["Trial"]:
        """Build from a raw /studies item. Returns None if there is no NCT ID."""
        proto = study.get("protocolSection") or {}
        nct_id = _get(proto, "identificationModule", "nctId", default="")
        if not nct_id:
            return None

        start_raw = _get(proto, "statusModule", "startDateStruct", "date", default="") or ""
        comp_raw = (
            _get(proto, "statusModule", "primaryCompletionDateStruct", "date", default="")
            or _get(proto, "statusModule", "completionDateStruct", "date", default="")
            or ""
        )
        enrollment = _get(proto, "designModule", "enrollmentInfo", "count")
        locations = _get(proto, "contactsLocationsModule", "locations", default=[]) or []
        countries = []
        for loc in locations:
            if isinstance(loc, dict) and loc.get("country"):
                country = str(loc["country"]).strip()
                if country and country not in countries:
                    countries.append(country)

        interventions = []
        for raw in _get(proto, "armsInterventionsModule", "interventions", default=[]) or []:
            if isinstance(raw, dict) and raw.get("name"):
                interventions.append(
                    Intervention(name=str(raw["name"]), type=str(raw.get("type") or "UNKNOWN"))
                )

        return cls(
            nct_id=str(nct_id),
            brief_title=_get(proto, "identificationModule", "briefTitle", default="") or "",
            official_title=_get(proto, "identificationModule", "officialTitle", default="") or "",
            overall_status=_get(proto, "statusModule", "overallStatus", default="UNKNOWN")
            or "UNKNOWN",
            study_type=_get(proto, "designModule", "studyType", default="UNKNOWN") or "UNKNOWN",
            phases=[str(p) for p in (_get(proto, "designModule", "phases", default=[]) or [])],
            conditions=[
                str(c) for c in (_get(proto, "conditionsModule", "conditions", default=[]) or [])
            ],
            interventions=interventions,
            lead_sponsor=_get(proto, "sponsorCollaboratorsModule", "leadSponsor", "name", default="")
            or "",
            lead_sponsor_class=_get(
                proto, "sponsorCollaboratorsModule", "leadSponsor", "class", default="UNKNOWN"
            )
            or "UNKNOWN",
            collaborators=[
                str(c.get("name"))
                for c in (
                    _get(proto, "sponsorCollaboratorsModule", "collaborators", default=[]) or []
                )
                if isinstance(c, dict) and c.get("name")
            ],
            start_date=_parse_partial_date(start_raw),
            start_date_raw=start_raw,
            completion_date=_parse_partial_date(comp_raw),
            completion_date_raw=comp_raw,
            enrollment=int(enrollment) if isinstance(enrollment, (int, float)) else None,
            countries=countries,
        )


PHASE_LABELS = {
    "EARLY_PHASE1": "Early Phase 1",
    "PHASE1": "Phase 1",
    "PHASE2": "Phase 2",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "NA": "Not Applicable",
}

STATUS_LABELS = {
    "RECRUITING": "Recruiting",
    "NOT_YET_RECRUITING": "Not Yet Recruiting",
    "ACTIVE_NOT_RECRUITING": "Active, Not Recruiting",
    "COMPLETED": "Completed",
    "TERMINATED": "Terminated",
    "WITHDRAWN": "Withdrawn",
    "SUSPENDED": "Suspended",
    "ENROLLING_BY_INVITATION": "Enrolling by Invitation",
    "UNKNOWN": "Unknown",
}


def humanize(value: str, mapping: dict[str, str]) -> str:
    return mapping.get(value, value.replace("_", " ").title() if value else "Unknown")
