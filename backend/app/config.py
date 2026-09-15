"""Application configuration, loaded from environment variables / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Secrets never have a usable default."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # LLM (planning only)
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 30.0

    # ClinicalTrials.gov
    ctgov_base_url: str = "https://clinicaltrials.gov/api/v2"
    ctgov_timeout_seconds: float = 30.0
    ctgov_page_size: int = 1000
    ctgov_max_studies: int = 5000
    ctgov_cache_ttl_seconds: int = 900

    # Service
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"
    max_citations_per_datum: int = 5

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        """False for an empty key or an un-edited placeholder from .env.example.

        Without this, a fresh checkout would spend a doomed round-trip on every
        request before falling back to the deterministic planner.
        """
        key = self.llm_api_key.strip()
        return bool(key) and "your-key" not in key.lower() and key != "sk-..."


@lru_cache
def get_settings() -> Settings:
    return Settings()
