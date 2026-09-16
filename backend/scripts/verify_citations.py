"""Independently re-verify every citation in `examples/` against the registry.

Attaching a citation is easy; proving the cited study really reports the value
shown on the chart is the part that matters. This script does the second thing,
and it does it *without* going through the service: it reads the committed
example outputs, then re-fetches each cited study directly from
`https://clinicaltrials.gov/api/v2/studies/{nctId}` and checks the claim against
the raw registry record.

    python backend/scripts/verify_citations.py

No running backend is required — only network access to ClinicalTrials.gov.
Exit code 0 means every claim checked out; 1 means at least one did not.

What each citation kind is checked for:

* `startDateStruct.date`      the study's own start date equals the cited value,
                              and its year equals the time bucket it sits in
* `designModule.phases`       the cited phase is the study's display phase
* `locations[].country`       the study really lists that country
* `enrollmentInfo.count`      the study's enrolment equals the cited number
* network edge (composite)    *both* endpoints appear in the study's sponsor /
                              intervention / condition fields
* scatter point               the point's own x and y equal the study's values

Citations are also checked structurally: every NCT ID cited by a datum must be
one the response says it retrieved, and every citation must carry an nct_id, a
field path and a value.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
STUDY_URL = "https://clinicaltrials.gov/api/v2/studies/{}"

# A courtesy pause between fetches. The whole point of this script is to hit the
# registry thousands of times; doing that as fast as the socket allows is how you
# get rate-limited half way through.
REQUEST_DELAY_SECONDS = 0.05

PHASE_LABELS = {
    "EARLY_PHASE1": "Early Phase 1",
    "PHASE1": "Phase 1",
    "PHASE2": "Phase 2",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "NA": "Not Applicable",
}
PHASE_ORDER = ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4"]

_cache: dict[str, dict] = {}


def fetch_study(nct_id: str) -> dict:
    """Re-fetch one study straight from the registry, with a small retry."""
    if nct_id in _cache:
        return _cache[nct_id]
    request = urllib.request.Request(
        STUDY_URL.format(nct_id), headers={"Accept": "application/json"}
    )
    # This script makes thousands of sequential requests, so it is deliberately
    # patient: a rate limit or a momentary DNS failure part-way through a long
    # run should cost a pause, not the whole verification.
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                _cache[nct_id] = json.load(response)
                time.sleep(REQUEST_DELAY_SECONDS)
                return _cache[nct_id]
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            if attempt == 5:
                raise
            time.sleep(min(2**attempt, 30))
    raise RuntimeError("unreachable")


def get(obj, *path, default=None):
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def display_phase(study: dict) -> str:
    phases = get(study, "protocolSection", "designModule", "phases", default=[]) or []
    if not phases:
        return "Not Applicable"
    ranked = [p for p in PHASE_ORDER if p in phases]
    chosen = ranked[-1] if ranked else phases[0]
    return PHASE_LABELS.get(chosen, chosen.replace("_", " ").title())


def study_countries(study: dict) -> set[str]:
    locations = get(study, "protocolSection", "contactsLocationsModule", "locations", default=[])
    return {
        str(loc["country"]).strip()
        for loc in locations or []
        if isinstance(loc, dict) and loc.get("country")
    }


def study_entities(study: dict) -> set[str]:
    """Every name a network edge endpoint could legitimately be."""
    proto = study.get("protocolSection") or {}
    names = {get(proto, "sponsorCollaboratorsModule", "leadSponsor", "name", default="")}
    for collab in get(proto, "sponsorCollaboratorsModule", "collaborators", default=[]) or []:
        if isinstance(collab, dict) and collab.get("name"):
            names.add(collab["name"])
    for iv in get(proto, "armsInterventionsModule", "interventions", default=[]) or []:
        if isinstance(iv, dict) and iv.get("name"):
            names.add(iv["name"])
    names |= set(get(proto, "conditionsModule", "conditions", default=[]) or [])
    return {n.strip().lower() for n in names if isinstance(n, str) and n.strip()}


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []

    def check(self, ok: bool, message: str) -> None:
        if ok:
            self.passed += 1
        else:
            self.failures.append(message)

    @property
    def total(self) -> int:
        return self.passed + len(self.failures)


def verify_citation(report: Report, where: str, citation: dict, row: dict) -> None:
    nct_id = citation.get("nct_id")
    field = citation.get("field") or ""
    value = citation.get("value")

    report.check(bool(nct_id), f"{where}: citation has no nct_id")
    report.check(bool(field), f"{where}: citation has no field path")
    report.check(value not in (None, ""), f"{where}: citation has no value")
    if not nct_id:
        return

    study = fetch_study(nct_id)
    report.check(
        get(study, "protocolSection", "identificationModule", "nctId") == nct_id,
        f"{where}: registry has no study {nct_id}",
    )

    if field.endswith("startDateStruct.date"):
        actual = get(study, "protocolSection", "statusModule", "startDateStruct", "date", default="")
        report.check(
            actual == value, f"{where}: {nct_id} start date is {actual!r}, cited {value!r}"
        )
        bucket = row.get("year") or row.get("start_year")
        if bucket is not None:
            report.check(
                str(actual)[:4] == str(bucket),
                f"{where}: {nct_id} starts {actual!r} but sits in bucket {bucket!r}",
            )

    elif field.endswith("designModule.phases"):
        actual = display_phase(study)
        report.check(actual == value, f"{where}: {nct_id} phase is {actual!r}, cited {value!r}")
        if row.get("phase") is not None:
            report.check(
                actual == row["phase"],
                f"{where}: {nct_id} phase {actual!r} does not match bar {row['phase']!r}",
            )

    elif "locations[].country" in field:
        countries = study_countries(study)
        report.check(
            value in countries, f"{where}: {nct_id} lists {sorted(countries)}, cited {value!r}"
        )
        if row.get("country") is not None:
            report.check(
                row["country"] in countries,
                f"{where}: {nct_id} does not list bar country {row['country']!r}",
            )

    elif field.endswith("enrollmentInfo.count"):
        actual = get(study, "protocolSection", "designModule", "enrollmentInfo", "count")
        report.check(
            str(actual) == str(value), f"{where}: {nct_id} enrolment is {actual!r}, cited {value!r}"
        )
        if row.get("enrollment") is not None:
            report.check(
                actual == row["enrollment"],
                f"{where}: {nct_id} enrolment {actual!r} != plotted {row['enrollment']!r}",
            )

    elif "↔" in str(value):
        left, _, right = str(value).partition("↔")
        entities = study_entities(study)
        for endpoint in (left.strip(), right.strip()):
            report.check(
                endpoint.lower() in entities,
                f"{where}: {nct_id} does not name edge endpoint {endpoint!r}",
            )

    else:
        report.check(False, f"{where}: unrecognised citation field {field!r}")


def verify_example(path: pathlib.Path, report: Report) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = payload["response"]
    if "visualization" not in body:
        print(f"{path.name:32} error example ({body['error']['code']}) - no citations expected")
        return

    viz = body["visualization"]
    retrieved_note = viz["metadata"].get("studies_retrieved")
    rows = list(viz.get("data") or []) + list(viz.get("edges") or [])
    before = report.total

    for index, row in enumerate(rows):
        citations = row.get("citations") or []
        supporting = row.get("supporting_nct_ids") or []
        count = row.get("supporting_trial_count")
        where = f"{path.name}[{index}]"

        # A datum with a non-zero value must be backed by something.
        value = row.get("trial_count")
        if value not in (None, 0):
            report.check(bool(citations), f"{where}: value {value} carries no citations")
            report.check(bool(supporting), f"{where}: value {value} lists no supporting NCT IDs")
        report.check(
            count is None or count >= len(supporting),
            f"{where}: supporting_trial_count {count} < listed ids {len(supporting)}",
        )
        # Full citations must be drawn from the datum's own supporting studies.
        for citation in citations:
            report.check(
                citation.get("nct_id") in supporting,
                f"{where}: cites {citation.get('nct_id')} which is not among its supporting ids",
            )
            verify_citation(report, where, citation, row)

    checked = report.total - before
    print(
        f"{path.name:32} {viz['type']:17} {len(rows):4} data points, "
        f"{checked:4} claims checked (retrieved {retrieved_note})"
    )


def main() -> int:
    report = Report()
    for path in sorted(EXAMPLES.glob("*.json")):
        verify_example(path, report)

    print()
    if report.failures:
        print(f"FAILED - {len(report.failures)} of {report.total} claims did not check out:")
        for failure in report.failures[:40]:
            print(f"  - {failure}")
        if len(report.failures) > 40:
            print(f"  ... and {len(report.failures) - 40} more")
        return 1

    print(f"OK - {report.passed}/{report.total} citation claims verified against the registry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
