"""Async ClinicalTrials.gov v2 API client: retries, pagination, TTL cache."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings
from app.logging_utils import log_event

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


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
                if response.status_code == 400:
                    raise CTGovError(
                        f"ClinicalTrials.gov rejected the query: {response.text[:200]}",
                        code="CTGOV_BAD_QUERY",
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise CTGovError("unexpected ClinicalTrials.gov response shape")
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
    ) -> list[dict]:
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
        pages = 0
        while len(studies) < cap:
            page_params = dict(params)
            if page_token:
                page_params["pageToken"] = page_token
            payload = await self._get("/studies", page_params)
            batch = payload.get("studies") or []
            if not isinstance(batch, list):
                raise CTGovError("ClinicalTrials.gov returned a malformed 'studies' field")
            studies.extend(batch)
            pages += 1
            page_token = payload.get("nextPageToken")
            if not page_token or not batch:
                break

        truncated = len(studies) >= cap and bool(page_token)
        log_event("ctgov_pagination_complete", pages=pages, studies=len(studies),
                  truncated=truncated)
        return studies[:cap]

    async def get_study(self, nct_id: str) -> dict:
        return await self._get(f"/studies/{nct_id}", {})

    async def field_values(self, field: str) -> dict:
        """/stats/field/values — used for cheap distribution sanity checks."""
        return await self._get("/stats/field/values", {"fields": field})
