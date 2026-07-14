"""Base class shared by every agent node.

Each agent is a small, focused unit with a single async :meth:`run` method that
takes the current :class:`~jobpilot.schemas.state.AgentState` and returns a
partial state update. Agents work with **or without** an LLM: when no model is
configured (e.g. no API key, or an LLM error at runtime) they fall back to a
deterministic heuristic so the whole pipeline stays runnable and testable.
"""

from __future__ import annotations

from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from jobpilot.config import Settings
from jobpilot.logging_config import get_logger
from jobpilot.schemas.state import AgentState

T = TypeVar("T", bound=BaseModel)


class BaseAgent:
    """Common wiring for agent nodes: settings, an optional LLM, logging."""

    #: Stable identifier used in logs and log entries.
    name: str = "base"

    def __init__(self, settings: Settings, llm: BaseChatModel | None = None) -> None:
        self.settings = settings
        self.llm = llm
        self.logger = get_logger(f"agent.{self.name}")

    @property
    def use_llm(self) -> bool:
        """Whether an LLM back-end is available for this agent."""
        return self.llm is not None

    async def _structured(self, schema: type[T], system: str, human: str) -> T:
        """Invoke the LLM and coerce the reply into ``schema``."""
        assert self.llm is not None  # guarded by callers via ``use_llm``
        model = self.llm.with_structured_output(schema)
        result = await model.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
        return result  # type: ignore[return-value]

    async def _text(self, system: str, human: str) -> str:
        """Invoke the LLM and return plain text."""
        assert self.llm is not None
        resp = await self.llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
        content = resp.content
        if isinstance(content, list):  # some providers return content blocks
            parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
            content = " ".join(parts)
        return str(content).strip()

    async def run(self, state: AgentState) -> dict:  # pragma: no cover - abstract
        raise NotImplementedError

    # LangGraph calls nodes as plain callables; expose ``run`` as ``__call__``.
    async def __call__(self, state: AgentState) -> dict:
        return await self.run(state)
