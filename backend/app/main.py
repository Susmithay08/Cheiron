"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.planner import Planner
from app.api.routes import router
from app.config import get_settings
from app.logging_utils import configure_logging, log_event

DESCRIPTION = """
Turns natural-language clinical-trial questions into **validated, renderable
visualization specifications** backed by live ClinicalTrials.gov data.

**How it works**

1. An LLM planner converts the question into a structured plan, constrained to a
   fixed vocabulary of intents, dimensions, metrics and chart types.
2. The plan is validated; anything outside the vocabulary is rejected.
3. Deterministic Python retrieves studies from the ClinicalTrials.gov v2 API,
   normalizes them, and computes every number in the chart.
4. A builder emits the visualization contract, with deep citations linking each
   datum back to the NCT IDs and field values that produced it.
5. An output validator checks the spec is renderable before it is returned.

The LLM never produces a count, a year, a sponsor name or an NCT ID.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.http_client = httpx.AsyncClient(
        base_url=settings.ctgov_base_url,
        timeout=settings.ctgov_timeout_seconds,
        headers={"Accept": "application/json"},
    )
    app.state.planner = Planner()
    log_event("startup", llm_configured=settings.llm_enabled, model=settings.llm_model)
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        log_event("shutdown")


app = FastAPI(
    title="ClinicalTrials.gov Query-to-Visualization Agent",
    version="1.0.0",
    description=DESCRIPTION,
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Frontend-friendly shape for schema violations."""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_REQUEST",
                "message": "The request did not match the expected schema.",
                "details": {
                    "fields": [
                        {"field": ".".join(str(p) for p in e["loc"][1:]), "problem": e["msg"]}
                        for e in exc.errors()[:10]
                    ]
                },
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    """Never leak a stack trace to the client; the details go to the log."""
    log_event("unhandled_exception", error=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred while handling the request.",
                "details": {},
            }
        },
    )
