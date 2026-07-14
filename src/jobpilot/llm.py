"""Configurable LLM factory.

JobPilot talks to language models through the LangChain ``BaseChatModel``
interface, which keeps the agents provider-agnostic. Anthropic's Claude is the
default and recommended back-end; OpenAI is available as an optional extra.

The factory is intentionally lazy: provider SDKs are imported only when their
provider is selected, so installing the OpenAI extra is optional.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from jobpilot.config import Settings, get_settings


class LLMConfigurationError(RuntimeError):
    """Raised when an LLM back-end cannot be constructed from settings."""


def build_llm(settings: Settings | None = None) -> BaseChatModel:
    """Construct a chat model from settings.

    Args:
        settings: Configuration to use. Defaults to the process settings.

    Returns:
        A ready-to-use LangChain chat model.

    Raises:
        LLMConfigurationError: If the provider is unknown or its SDK/extra is
            not installed.
    """
    settings = settings or get_settings()
    provider = settings.llm_provider

    if provider == "anthropic":
        return _build_anthropic(settings)
    if provider == "openai":
        return _build_openai(settings)
    raise LLMConfigurationError(f"Unsupported LLM provider: {provider!r}")


def _build_anthropic(settings: Settings) -> BaseChatModel:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:  # pragma: no cover - dependency always present
        raise LLMConfigurationError(
            "langchain-anthropic is not installed. Install the base package."
        ) from exc

    kwargs: dict[str, object] = {
        "model": settings.llm_model,
        "max_tokens": settings.llm_max_tokens,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
    }
    # Only send temperature when explicitly configured — several current Claude
    # models reject the parameter outright.
    if settings.llm_temperature is not None:
        kwargs["temperature"] = settings.llm_temperature
    if settings.anthropic_api_key:
        kwargs["api_key"] = settings.anthropic_api_key

    return ChatAnthropic(**kwargs)


def _build_openai(settings: Settings) -> BaseChatModel:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise LLMConfigurationError(
            "The OpenAI provider requires the 'openai' extra. "
            'Install it with: pip install "jobpilot[openai]"'
        ) from exc

    kwargs: dict[str, object] = {
        "model": settings.llm_model,
        "max_tokens": settings.llm_max_tokens,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
    }
    if settings.llm_temperature is not None:
        kwargs["temperature"] = settings.llm_temperature
    if settings.openai_api_key:
        kwargs["api_key"] = settings.openai_api_key
    # Custom OpenAI-compatible endpoint (e.g. OpenRouter, DeepSeek, a local server).
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url

    return ChatOpenAI(**kwargs)


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Return a cached chat model built from the process settings."""
    return build_llm()
