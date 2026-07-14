"""Tests for settings/configuration."""

from __future__ import annotations

from jobpilot.config import Settings, get_settings, reload_settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm_provider == "anthropic"
    assert s.llm_model == "claude-opus-4-8"
    assert s.search_provider == "sample"
    assert s.browser_mode == "auto"
    assert s.browser_allow_submit is True


def test_active_api_key_follows_provider():
    s = Settings(_env_file=None, anthropic_api_key="a-key", openai_api_key="o-key")
    assert s.active_api_key == "a-key"
    s2 = s.model_copy(update={"llm_provider": "openai"})
    assert s2.active_api_key == "o-key"


def test_log_level_normalised():
    assert Settings(_env_file=None, log_level="debug").log_level == "DEBUG"


def test_ensure_dirs(tmp_path):
    target = tmp_path / "artifacts" / "nested"
    Settings(_env_file=None, artifacts_dir=target).ensure_dirs()
    assert target.exists()


def test_env_prefix_and_key_alias(monkeypatch):
    monkeypatch.setenv("JOBPILOT_LLM_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    s = Settings(_env_file=None)
    assert s.llm_model == "claude-sonnet-5"
    assert s.anthropic_api_key == "from-env"


def test_get_settings_is_cached(monkeypatch):
    monkeypatch.delenv("JOBPILOT_LLM_MODEL", raising=False)
    first = get_settings()
    assert get_settings() is first
    refreshed = reload_settings()
    assert refreshed is not first
