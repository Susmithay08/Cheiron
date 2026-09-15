"""Query planner: natural language -> validated QueryPlan.

Two layers, in order:
  1. The LLM proposes a plan (constrained to the controlled vocabulary).
  2. Pydantic validates it. Invalid plans get exactly one repair attempt, then
     we fall back to a deterministic keyword planner rather than guessing.

The caller's structured filters always win over anything the LLM inferred.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import ValidationError

from app.agent.intent import (
    Dimension,
    Intent,
    NumericField,
    Phase,
    QueryPlan,
    RelationshipKind,
    TrialStatus,
)
from app.agent.llm import LLMClient, LLMError
from app.agent.prompts import PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE
from app.logging_utils import log_event


class PlanningError(RuntimeError):
    def __init__(self, message: str, *, code: str = "PLANNING_FAILED"):
        super().__init__(message)
        self.code = code


class Planner:
    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or LLMClient()

    async def plan(self, query: str, structured: dict[str, Any]) -> tuple[QueryPlan, str]:
        """Return (plan, planner_mode) where mode is 'llm' or 'heuristic'."""
        structured = {k: v for k, v in structured.items() if v not in (None, [], "")}

        if self.llm.enabled:
            try:
                raw = await self._ask_llm(query, structured)
                plan = self._validate(raw)
                plan = self._apply_structured(plan, structured)
                log_event("planner_completed", mode="llm", intent=plan.intent.value)
                return plan, "llm"
            except (LLMError, PlanningError) as exc:
                log_event("planner_llm_failed", error=str(exc)[:200])

        plan = self._apply_structured(heuristic_plan(query, structured), structured)
        log_event("planner_completed", mode="heuristic", intent=plan.intent.value)
        return plan, "heuristic"

    async def _ask_llm(self, query: str, structured: dict[str, Any]) -> dict:
        user = PLANNER_USER_TEMPLATE.format(
            query=query, structured=json.dumps(structured, default=str) or "{}"
        )
        raw = await self.llm.complete_json(PLANNER_SYSTEM_PROMPT, user)
        try:
            self._validate(raw)
            return raw
        except PlanningError as exc:
            # One bounded repair round: hand the validation error back.
            log_event("planner_repair_attempt", error=str(exc)[:200])
            repair = (
                f"{user}\n\nYour previous answer was rejected:\n{exc}\n"
                "Return a corrected JSON plan using only the allowed values."
            )
            return await self.llm.complete_json(PLANNER_SYSTEM_PROMPT, repair)

    @staticmethod
    def _validate(raw: dict) -> QueryPlan:
        """Strict validation. Unknown keys are dropped, bad values are fatal."""
        allowed = set(QueryPlan.model_fields)
        cleaned = {k: v for k, v in raw.items() if k in allowed}
        try:
            return QueryPlan.model_validate(cleaned)
        except ValidationError as exc:
            messages = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5]
            )
            raise PlanningError(
                f"planner output rejected ({messages})", code="INVALID_PLAN"
            ) from exc

    @staticmethod
    def _apply_structured(plan: QueryPlan, structured: dict[str, Any]) -> QueryPlan:
        """Caller-supplied filters override LLM inference."""
        data = plan.model_dump()
        filters = data["filters"]
        for key in ("start_year", "end_year", "sponsor", "country"):
            if structured.get(key) is not None:
                filters[key] = structured[key]
        if structured.get("status"):
            filters["statuses"] = [structured["status"]]
        if structured.get("trial_phase"):
            filters["phases"] = [structured["trial_phase"]]

        # An explicit drug/condition becomes the search term when the LLM had none.
        explicit = [structured.get(k) for k in ("drug_name", "condition") if structured.get(k)]
        if explicit and not data["search_terms"]:
            data["search_terms"] = explicit
            data["series_labels"] = explicit
        elif explicit and len(data["search_terms"]) == 1:
            # Refine a single generic term with the caller-supplied entity.
            merged = " ".join(dict.fromkeys(data["search_terms"] + explicit))
            data["search_terms"] = [merged]
            data["series_labels"] = [explicit[0]]
        return QueryPlan.model_validate(data)


# --------------------------------------------------------------------------
# Deterministic fallback planner
# --------------------------------------------------------------------------

_STOPWORDS = {
    "how", "has", "have", "the", "number", "of", "trials", "trial", "for", "this",
    "drug", "changed", "over", "time", "show", "me", "what", "are", "which",
    "compare", "versus", "and", "per", "year", "since", "distributed", "across",
    "phases", "phase", "most", "with", "network", "graph", "between", "study",
    "studies", "many", "started", "each", "countries", "country", "count",
    "counts", "chart", "plot", "there", "relationship", "correlation", "trends",
    "recruiting", "sponsor", "sponsors", "drugs", "enrollment", "start",
}

_INTENT_PATTERNS: list[tuple[Intent, tuple[str, ...]]] = [
    (Intent.RELATIONSHIP, ("network", "co-occur", "cooccur", "graph of")),
    (Intent.CORRELATION, ("correlat", "scatter", "vs enrollment", "against enrollment")),
    (Intent.COMPARISON, (" vs ", " versus ", "compare")),
    (Intent.GEOGRAPHIC, ("country", "countries", "geograph", "where are")),
    (Intent.TIME_TREND, ("over time", "per year", "each year", "by year", "trend", "since")),
    (Intent.DISTRIBUTION, ("distribut", "breakdown", "across phases", "by phase", "how are")),
]

_DIMENSION_PATTERNS: list[tuple[Dimension, tuple[str, ...]]] = [
    (Dimension.PHASE, ("phase",)),
    (Dimension.STATUS, ("status", "recruiting")),
    (Dimension.INTERVENTION_TYPE, ("intervention type", "intervention types", "intervention")),
    (Dimension.STUDY_TYPE, ("study type", "observational", "interventional")),
    (Dimension.SPONSOR_CLASS, ("sponsor categor", "sponsor class", "industry")),
    (Dimension.SPONSOR, ("sponsor",)),
    (Dimension.CONDITION, ("condition", "disease")),
    (Dimension.COUNTRY, ("country", "countries")),
    (Dimension.ENROLLMENT, ("enrollment",)),
]

_RELATIONSHIP_PATTERNS: list[tuple[RelationshipKind, tuple[str, ...]]] = [
    (RelationshipKind.SPONSOR_DRUG, ("sponsor",)),
    (RelationshipKind.DRUG_DRUG, ("combination", "co-occur", "drug network")),
    (RelationshipKind.CONDITION_INTERVENTION, ("condition", "intervention")),
]


def heuristic_plan(query: str, structured: dict[str, Any]) -> QueryPlan:
    """Keyword-based planner used when the LLM is unavailable or unusable.

    Intentionally simple: it keeps the service demonstrable without a key and
    gives the LLM path a safety net, but it is not the primary code path.
    """
    text = f" {query.lower().strip()} "

    intent = Intent.DISTRIBUTION
    for candidate, needles in _INTENT_PATTERNS:
        if any(n in text for n in needles):
            intent = candidate
            break

    terms = _extract_terms(query, structured, intent)
    if intent == Intent.COMPARISON and len(terms) < 2:
        intent = Intent.DISTRIBUTION

    dimension = None
    for candidate, needles in _DIMENSION_PATTERNS:
        if any(n in text for n in needles):
            dimension = candidate
            break

    relationship = None
    if intent == Intent.RELATIONSHIP:
        relationship = RelationshipKind.SPONSOR_DRUG
        for candidate, needles in _RELATIONSHIP_PATTERNS:
            if any(n in text for n in needles):
                relationship = candidate
                break

    statuses = [TrialStatus.RECRUITING] if "recruiting" in text else []
    phases = [Phase.PHASE3] if "phase 3" in text or "phase iii" in text else []
    year_match = re.search(r"(?:since|after|from)\s+(\d{4})", text)
    start_year = int(year_match.group(1)) if year_match else None

    return QueryPlan(
        intent=intent,
        search_terms=terms,
        series_labels=terms,
        filters={"statuses": statuses, "phases": phases, "start_year": start_year},
        dimension=dimension,
        relationship=relationship,
        x_field=NumericField.START_YEAR if intent == Intent.CORRELATION else None,
        y_field=NumericField.ENROLLMENT if intent == Intent.CORRELATION else None,
        interpretation=f"Keyword-derived plan for: {query.strip()[:200]}",
        assumptions=["Plan derived by the deterministic keyword planner (LLM unavailable)."],
    )


def _extract_terms(query: str, structured: dict[str, Any], intent: Intent) -> list[str]:
    explicit = [structured[k] for k in ("drug_name", "condition") if structured.get(k)]
    if explicit:
        return explicit

    lowered = query.lower()
    if intent == Intent.COMPARISON:
        parts = re.split(r"\s+vs\.?\s+|\s+versus\s+", lowered)
        if len(parts) >= 2:
            cleaned = [c for c in (_keywords(p) for p in parts) if c]
            if len(cleaned) >= 2:
                return cleaned[:4]

    keywords = _keywords(lowered)
    return [keywords] if keywords else []


def _keywords(text: str) -> str:
    words = re.findall(r"[a-z0-9\-]+", text)
    kept = [w for w in words if w not in _STOPWORDS and not w.isdigit() and len(w) > 2]
    return " ".join(kept[:5])
