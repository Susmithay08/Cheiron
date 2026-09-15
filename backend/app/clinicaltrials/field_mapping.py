"""Which CT.gov API fields to request, driven by the execution plan.

Fetching every field for thousands of studies is slow and wasteful, so the
executor asks for only the fields the chosen aggregation actually reads.
"""

from app.agent.intent import Dimension, Intent, NumericField, QueryPlan

# Always needed: identity + title (titles are used as citation excerpts).
BASE_FIELDS = [
    "NCTId",
    "BriefTitle",
]

DIMENSION_FIELDS: dict[Dimension, list[str]] = {
    Dimension.YEAR: ["StartDate"],
    Dimension.PHASE: ["Phase"],
    Dimension.STATUS: ["OverallStatus"],
    Dimension.STUDY_TYPE: ["StudyType"],
    Dimension.INTERVENTION_TYPE: ["InterventionType", "InterventionName"],
    Dimension.COUNTRY: ["LocationCountry"],
    Dimension.SPONSOR: ["LeadSponsorName", "LeadSponsorClass"],
    Dimension.SPONSOR_CLASS: ["LeadSponsorClass", "LeadSponsorName"],
    Dimension.CONDITION: ["Condition"],
    Dimension.ENROLLMENT: ["EnrollmentCount"],
}

NUMERIC_FIELDS: dict[NumericField, list[str]] = {
    NumericField.ENROLLMENT: ["EnrollmentCount"],
    NumericField.START_YEAR: ["StartDate"],
    NumericField.DURATION_DAYS: ["StartDate", "PrimaryCompletionDate", "CompletionDate"],
}

RELATIONSHIP_FIELDS = [
    "LeadSponsorName",
    "LeadSponsorClass",
    "InterventionName",
    "InterventionType",
    "Condition",
]


def fields_for_plan(plan: QueryPlan) -> list[str]:
    """Return the deduplicated CT.gov field list required to execute `plan`."""
    fields = list(BASE_FIELDS)

    if plan.intent == Intent.RELATIONSHIP:
        fields += RELATIONSHIP_FIELDS
    elif plan.intent == Intent.CORRELATION:
        for nf in (plan.x_field, plan.y_field):
            if nf:
                fields += NUMERIC_FIELDS[nf]
        fields += ["Phase"]  # used to colour scatter points
    elif plan.dimension:
        fields += DIMENSION_FIELDS[plan.dimension]

    # Client-side filters need their own fields present.
    if plan.filters.start_year or plan.filters.end_year:
        fields += ["StartDate"]
    if plan.metric.value.startswith("enrollment"):
        fields += ["EnrollmentCount"]

    seen: set[str] = set()
    return [f for f in fields if not (f in seen or seen.add(f))]
