"""Minimal OpenAI-compatible chat client.

Deliberately dependency-free (plain httpx) so the service is not coupled to a
vendor SDK; any OpenAI-compatible base URL works.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx

from app.config import Settings, get_settings
from app.logging_utils import log_event


class LLMError(RuntimeError):
    def __init__(self, message: str, *, code: str = "LLM_UNAVAILABLE"):
        super().__init__(message)
        self.code = code


class LLMClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.llm_enabled

    async def complete_json(self, system: str, user: str) -> dict:
        """Ask the model for a JSON object and parse it. Raises LLMError."""
        if not self.enabled:
            raise LLMError("no LLM_API_KEY configured", code="LLM_NOT_CONFIGURED")

        body = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                    json=body,
                )
                if response.status_code >= 400:
                    raise LLMError(f"LLM returned HTTP {response.status_code}")
                content = response.json()["choices"][0]["message"]["content"]
        except LLMError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"LLM call failed: {exc}") from exc

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM returned non-JSON content: {exc}", code="LLM_BAD_OUTPUT") from exc
        if not isinstance(parsed, dict):
            raise LLMError("LLM returned JSON that is not an object", code="LLM_BAD_OUTPUT")
        log_event("llm_completed", model=self.settings.llm_model, keys=sorted(parsed)[:12])
        return parsed
