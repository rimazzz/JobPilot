"""Application settings.

Configuration is loaded from environment variables (prefixed ``JOBPILOT_``) and
an optional ``.env`` file. Provider API keys use their conventional unprefixed
names (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["anthropic", "openai"]
SearchProvider = Literal["sample", "greenhouse", "remoteok", "remotive", "remote"]
BrowserMode = Literal["auto", "playwright", "simulated"]
LogFormat = Literal["json", "console"]


class Settings(BaseSettings):
    """Runtime configuration for JobPilot."""

    model_config = SettingsConfigDict(
        env_prefix="JOBPILOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # Allow the provider-key fields to be set either by their unprefixed env
        # alias (ANTHROPIC_API_KEY) or by their Python name (e.g. in tests/DI).
        populate_by_name=True,
    )

    # -- LLM -----------------------------------------------------------------
    llm_provider: LLMProvider = "anthropic"
    llm_model: str = "claude-opus-4-8"
    llm_max_tokens: int = Field(default=4096, ge=1)
    llm_temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    llm_timeout_seconds: float = Field(default=120.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    #: Custom base URL for an OpenAI-compatible endpoint (OpenRouter, DeepSeek,
    #: Together, Groq, a local server, ...). Only used by the "openai" provider.
    llm_base_url: str | None = None

    # Provider keys use their conventional unprefixed env var names.
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")

    # -- Job search ----------------------------------------------------------
    search_provider: SearchProvider = "sample"
    search_api_url: str | None = None
    search_api_key: str | None = None
    max_jobs: int = Field(default=5, ge=1, le=50)
    #: Comma-separated Greenhouse board slugs to search when provider=greenhouse.
    #: These companies expose real, fillable application forms.
    greenhouse_companies: str = (
        "coinbase,stripe,databricks,figma,instacart,robinhood,discord,gusto,airtable,dropbox"
    )

    # -- Browser automation --------------------------------------------------
    #: "auto"       -> use Playwright for live http(s) forms, otherwise simulate.
    #: "playwright" -> always drive a real browser.
    #: "simulated"  -> never launch a browser; fabricate a standard form offline.
    browser_mode: BrowserMode = "auto"
    browser_headless: bool = True
    #: A hard safety switch. Even when true, submission still requires explicit
    #: human approval; when false, the submit step is skipped entirely.
    browser_allow_submit: bool = True
    browser_timeout_ms: int = Field(default=30_000, ge=1_000)
    artifacts_dir: Path = Path("artifacts")

    # -- Runtime -------------------------------------------------------------
    log_level: str = "INFO"
    log_format: LogFormat = "console"
    checkpoint_db: str = "checkpoints.sqlite"

    @field_validator("log_level")
    @classmethod
    def _normalise_level(cls, value: str) -> str:
        return value.upper()

    def ensure_dirs(self) -> None:
        """Create runtime directories that other components rely on."""
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    @property
    def active_api_key(self) -> str | None:
        """The API key for the currently selected LLM provider, if any."""
        return self.anthropic_api_key if self.llm_provider == "anthropic" else self.openai_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Cached so the same configuration object is shared across the process.
    Call :func:`reload_settings` in tests to pick up patched environments.
    """
    return Settings()


def reload_settings() -> Settings:
    """Clear the settings cache and return a freshly loaded instance."""
    get_settings.cache_clear()
    return get_settings()
