"""Async ClinicalTrials.gov v2 API client: retries, pagination, TTL cache."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings
from app.logging_utils import log_event

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# 4xx responses that are the *caller's* fault. Retrying them burns time and
# rate-limit budget for a result that cannot change, so they fail immediately.
NON_RETRYABLE_CLIENT_CODES = {
    400: "CTGOV_BAD_QUERY",
    401: "CTGOV_CLIENT_ERROR",
    403: "CTGOV_CLIENT_ERROR",
    404: "CTGOV_NOT_FOUND",
    405: "CTGOV_CLIENT_ERROR",
    410: "CTGOV_NOT_FOUND",
    422: "CTGOV_BAD_QUERY",
}


@dataclass(slots=True)
class SearchResult:
    """One search arm: the studies fetched plus how that fetch went.

    `truncated` is the honest answer to "is this every matching study?", and it
    is the only thing the response metadata should be derived from — counting
    rows and comparing them to a cap gets the answer wrong as soon as a request
    has more than one search arm.
    """

    studies: list[dict] = field(default_factory=list)
    truncated: bool = False
    pages_fetched: int = 0
    total_available: Optional[int] = None

    def __len__(self) -> int:
        return len(self.studies)

    def __iter__(self):
        return iter(self.studies)


class CTGovError(RuntimeError):
    """Raised when ClinicalTrials.gov cannot be reached or returns garbage."""

    def __init__(self, message: str, *, code: str = "CTGOV_UNAVAILABLE"):
        super().__init__(message)
        self.code = code


class _TTLCache:
    """Tiny in-process cache. No Redis: a single-process demo does not need it."""

    def __init__(self, ttl_seconds: int, max_entries: int = 256):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        if self.ttl <= 0:
            return None
        hit = self._store.get(key)
        if not hit:
            return None
        stored_at, value = hit
        if time.time() - stored_at > self.ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if self.ttl <= 0:
            return
        if len(self._store) >= self.max_entries:
            oldest = min(self._store, key=lambda k: self._store[k][0])
            self._store.pop(oldest, None)
        self._store[key] = (time.time(), value)


class ClinicalTrialsClient:
    """Thin, well-behaved wrapper over the CT.gov v2 REST API."""

    def __init__(self, settings: Optional[Settings] = None, client: Optional[httpx.AsyncClient] = None):
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self._cache = _TTLCache(self.settings.ctgov_cache_ttl_seconds)

    async def __aenter__(self) -> "ClinicalTrialsClient":
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.ctgov_base_url,
                timeout=self.settings.ctgov_timeout_seconds,
                headers={"Accept": "application/json"},
            )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---- transport -------------------------------------------------------
    async def _get(self, path: str, params: dict[str, Any], *, attempts: int = 3) -> dict:
        if self._client is None:
            raise CTGovError("client used outside of an async context manager")

        cache_key = f"{path}?{json.dumps(params, sort_keys=True)}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            log_event("ctgov_cache_hit", path=path)
            return cached

        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                log_event("ctgov_request", path=path, attempt=attempt,
                          page_size=params.get("pageSize"))
                response = await self._client.get(path, params=params)
                if response.status_code in RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                if response.status_code in NON_RETRYABLE_CLIENT_CODES:
                    raise CTGovError(
                        f"ClinicalTrials.gov rejected the request with HTTP "
                        f"{response.status_code}: {response.text[:200]}",
                        code=NON_RETRYABLE_CLIENT_CODES[response.status_code],
                    )
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError as exc:
                    # A 200 with an unparseable body is a server-side defect, not
                    # a transient blip; retrying it cannot help.
                    raise CTGovError(
                        f"ClinicalTrials.gov returned a body that is not JSON: {exc}",
                        code="CTGOV_BAD_RESPONSE",
                    ) from exc
                if not isinstance(payload, dict):
                    raise CTGovError(
                        "unexpected ClinicalTrials.gov response shape",
                        code="CTGOV_BAD_RESPONSE",
                    )
                self._cache.set(cache_key, payload)
                return payload
            except CTGovError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < attempts:
                    await asyncio.sleep(0.5 * 2 ** (attempt - 1))  # 0.5s, 1s
        raise CTGovError(f"ClinicalTrials.gov request failed: {last_error}")

    # ---- endpoints -------------------------------------------------------
    async def search_studies(
        self,
        *,
        query_term: Optional[str] = None,
        condition: Optional[str] = None,
        intervention: Optional[str] = None,
        sponsor: Optional[str] = None,
        location: Optional[str] = None,
        statuses: Optional[list[str]] = None,
        phases: Optional[list[str]] = None,
        study_type: Optional[str] = None,
        fields: Optional[list[str]] = None,
        max_studies: Optional[int] = None,
    ) -> SearchResult:
        """Fetch studies across as many pages as the cap allows.

        Returns raw study dicts; normalization happens in `Trial.from_api`.
        """
        cap = max_studies or self.settings.ctgov_max_studies
        params: dict[str, Any] = {
            "pageSize": min(self.settings.ctgov_page_size, cap),
            "countTotal": "true",
        }
        if query_term:
            params["query.term"] = query_term
        if condition:
            params["query.cond"] = condition
        if intervention:
            params["query.intr"] = intervention
        if sponsor:
            params["query.spons"] = sponsor
        if location:
            params["query.locn"] = location
        if fields:
            params["fields"] = ",".join(fields)

        advanced: list[str] = []
        if statuses:
            params["filter.overallStatus"] = ",".join(statuses)
        if phases:
            advanced.append("AREA[Phase](" + " OR ".join(phases) + ")")
        if study_type:
            advanced.append(f"AREA[StudyType]{study_type}")
        if advanced:
            params["filter.advanced"] = " AND ".join(advanced)

        studies: list[dict] = []
        page_token: Optional[str] = None
        seen_tokens: set[str] = set()
        repeated_token = False
        total_available: Optional[int] = None
        pages = 0
        while len(studies) < cap:
            page_params = dict(params)
            if page_token:
                page_params["pageToken"] = page_token
            payload = await self._get("/studies", page_params)
            batch = payload.get("studies") or []
            if not isinstance(batch, list):
                raise CTGovError(
                    "ClinicalTrials.gov returned a malformed 'studies' field",
                    code="CTGOV_BAD_RESPONSE",
                )
            if total_available is None and isinstance(payload.get("totalCount"), int):
                total_available = payload["totalCount"]
            studies.extend(batch)
            pages += 1

            next_token = payload.get("nextPageToken")
            if not next_token or not isinstance(next_token, str) or not batch:
                page_token = None
                break
            if next_token in seen_tokens:
                # A registry that hands back a token it already gave us would
                # otherwise spin until the cap. Stop and report truncation.
                log_event("ctgov_repeated_page_token", pages=pages)
                repeated_token = True
                page_token = next_token
                break
            seen_tokens.add(next_token)
            page_token = next_token

        truncated = repeated_token or (bool(page_token) and len(studies) >= cap)
        if total_available is not None and total_available > len(studies):
            truncated = True
        log_event("ctgov_pagination_complete", pages=pages, studies=len(studies),
                  truncated=truncated, total_available=total_available)
        return SearchResult(
            studies=studies[:cap],
            truncated=truncated,
            pages_fetched=pages,
            total_available=total_available,
        )

    async def get_study(self, nct_id: str) -> dict:
        return await self._get(f"/studies/{nct_id}", {})

    async def field_values(self, field: str) -> dict:
        """/stats/field/values — used for cheap distribution sanity checks."""
        return await self._get("/stats/field/values", {"fields": field})
