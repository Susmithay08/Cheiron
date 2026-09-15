"""HTTP surface: one analyze endpoint plus health and example queries."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.agent.planner import Planner, PlanningError
from app.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ErrorBody,
    ErrorResponse,
    ExampleQuery,
    PlanSummary,
    ResponseMeta,
)
from app.clinicaltrials.client import ClinicalTrialsClient, CTGovError
from app.config import get_settings
from app.execution.executor import Executor, ExecutionError
from app.logging_utils import log_event, request_id_var
from app.validation.validator import OutputValidationError, validate_visualization

router = APIRouter()

EXAMPLE_QUERIES = [
    ExampleQuery(
        label="Time trend",
        query="How has the number of trials for Pembrolizumab changed per year since 2015?",
        intent="time_trend",
    ),
    ExampleQuery(
        label="Distribution",
        query="How are breast cancer trials distributed across phases?",
        intent="distribution",
    ),
    ExampleQuery(
        label="Comparison",
        query="Compare trial counts by phase for Ozempic vs Wegovy",
        intent="comparison",
    ),
    ExampleQuery(
        label="Geography",
        query="Which countries have the most recruiting trials for Alzheimer's disease?",
        intent="geographic",
    ),
    ExampleQuery(
        label="Network",
        query="Show a network of sponsors and drugs for diabetes trials",
        intent="relationship",
    ),
    ExampleQuery(
        label="Correlation",
        query="Is there a relationship between enrollment and start year for melanoma trials?",
        intent="correlation",
    ),
]


def _error(code: str, message: str, details: dict, status: int, request_id: str) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details, request_id=request_id)
    )
    return JSONResponse(status_code=status, content=body.model_dump())


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "llm_configured": settings.llm_enabled,
        "llm_model": settings.llm_model if settings.llm_enabled else None,
        "ctgov_base_url": settings.ctgov_base_url,
    }


@router.get("/examples", response_model=list[ExampleQuery], summary="Demo queries")
async def examples() -> list[ExampleQuery]:
    """Curated queries that exercise every supported intent and chart type."""
    return EXAMPLE_QUERIES


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Unusable query or planner output"},
        404: {"model": ErrorResponse, "description": "No ClinicalTrials.gov studies matched"},
        502: {"model": ErrorResponse, "description": "ClinicalTrials.gov or the LLM failed"},
    },
    summary="Turn a clinical-trial question into a visualization specification",
)
async def analyze(payload: AnalyzeRequest, request: Request):
    """Plan the question, retrieve real studies, aggregate, and return a chart spec."""
    request_id = uuid.uuid4().hex[:12]
    request_id_var.set(request_id)
    started = time.perf_counter()
    settings = get_settings()
    log_event("request_received", query=payload.query[:200])

    planner: Planner = request.app.state.planner
    try:
        plan, planner_mode = await planner.plan(payload.query, payload.structured_filters())
    except PlanningError as exc:
        return _error(exc.code, str(exc), {}, 400, request_id)

    try:
        async with ClinicalTrialsClient(settings, request.app.state.http_client) as client:
            executor = Executor(client, settings)
            visualization = await executor.execute(plan)
            # Validate citations against what was actually retrieved, not
            # against what the builders happened to attach.
            validate_visualization(visualization, executor.retrieved_nct_ids)
    except ExecutionError as exc:
        status = 404 if exc.code == "NO_MATCHING_TRIALS" else 422
        if exc.code.startswith("CTGOV"):
            status = 502
        log_event("request_failed", code=exc.code)
        return _error(exc.code, str(exc), exc.details, status, request_id)
    except CTGovError as exc:
        log_event("request_failed", code=exc.code)
        return _error(exc.code, str(exc), {}, 502, request_id)
    except OutputValidationError as exc:
        log_event("request_failed", code=exc.code, problems=exc.problems)
        return _error(
            exc.code,
            "The generated visualization failed output validation and was not returned.",
            {"problems": exc.problems},
            500,
            request_id,
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    log_event("request_completed", elapsed_ms=elapsed_ms, type=visualization.type)

    return AnalyzeResponse(
        visualization=visualization,
        meta=ResponseMeta(
            request_id=request_id,
            query=payload.query,
            elapsed_ms=elapsed_ms,
            plan=PlanSummary(
                intent=plan.intent.value,
                search_terms=plan.search_terms,
                dimension=plan.dimension.value if plan.dimension else None,
                metric=plan.metric.value,
                relationship=plan.relationship.value if plan.relationship else None,
                filters=plan.filters.model_dump(exclude_none=True, exclude_defaults=True),
                interpretation=plan.interpretation,
                planner_mode=planner_mode,
            ),
        ),
    )
