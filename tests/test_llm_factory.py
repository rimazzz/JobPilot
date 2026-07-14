"""Tests for the configurable LLM factory."""

from __future__ import annotations

import importlib.util

import pytest
from langchain_core.language_models import BaseChatModel

from jobpilot.config import Settings
from jobpilot.llm import LLMConfigurationError, build_llm

_OPENAI_INSTALLED = importlib.util.find_spec("langchain_openai") is not None


def test_build_anthropic():
    settings = Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key="sk-test")
    llm = build_llm(settings)
    assert isinstance(llm, BaseChatModel)
    assert llm.model == "claude-opus-4-8"  # type: ignore[attr-defined]


@pytest.mark.skipif(_OPENAI_INSTALLED, reason="langchain-openai is installed")
def test_openai_requires_extra_when_missing():
    settings = Settings(_env_file=None, llm_provider="openai", openai_api_key="sk-test")
    with pytest.raises(LLMConfigurationError, match="openai"):
        build_llm(settings)


@pytest.mark.skipif(not _OPENAI_INSTALLED, reason="langchain-openai not installed")
def test_openai_builds_with_custom_base_url():
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        llm_model="deepseek/deepseek-chat",
        llm_base_url="https://openrouter.ai/api/v1",
        openai_api_key="sk-test",
    )
    llm = build_llm(settings)
    assert isinstance(llm, BaseChatModel)
    assert llm.model_name == "deepseek/deepseek-chat"  # type: ignore[attr-defined]


def test_unknown_provider():
    settings = Settings(_env_file=None).model_copy(update={"llm_provider": "bogus"})
    with pytest.raises(LLMConfigurationError, match="Unsupported"):
        build_llm(settings)


def test_temperature_only_sent_when_set():
    with_temp = Settings(_env_file=None, anthropic_api_key="x", llm_temperature=0.3)
    llm = build_llm(with_temp)
    assert llm.temperature == 0.3  # type: ignore[attr-defined]
