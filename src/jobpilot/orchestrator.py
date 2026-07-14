"""Run orchestration and the human-in-the-loop approval lifecycle.

The :class:`Orchestrator` owns a single compiled graph and drives it across the
approval breakpoint. A run is identified by a ``thread_id`` (the LangGraph
checkpoint key), so status can be polled and a decision applied in a later
request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from jobpilot.config import Settings, get_settings
from jobpilot.graph import APPROVAL_NODE, build_graph
from jobpilot.llm import build_llm
from jobpilot.logging_config import bind_context, clear_context, get_logger
from jobpilot.schemas.application import ApprovalDecision
from jobpilot.schemas.candidate import CandidateProfile
from jobpilot.schemas.state import AgentState, RunStatus

logger = get_logger("orchestrator")


class OrchestratorError(RuntimeError):
    """Raised for invalid run lifecycle operations (e.g. approving too early)."""


@dataclass
class RunSnapshot:
    """A point-in-time view of a run."""

    thread_id: str
    values: AgentState
    next: tuple[str, ...] = field(default_factory=tuple)

    @property
    def awaiting_approval(self) -> bool:
        return APPROVAL_NODE in self.next

    @property
    def status(self) -> RunStatus:
        return self.values.get("status", RunStatus.PENDING)


class Orchestrator:
    """Coordinates job-application runs over a compiled LangGraph workflow."""

    def __init__(
        self, settings: Settings | None = None, graph: CompiledStateGraph | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()
        self.graph = graph or self._default_graph()
        self._threads: set[str] = set()

    def _default_graph(self) -> CompiledStateGraph:
        llm = build_llm(self.settings) if self.settings.active_api_key else None
        if llm is None:
            logger.warning(
                "orchestrator.no_api_key",
                message="No LLM API key configured; agents run in heuristic mode.",
                provider=self.settings.llm_provider,
            )
        return build_graph(self.settings, llm=llm)

    @staticmethod
    def _config(thread_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": thread_id}}

    async def start_run(self, candidate: CandidateProfile, goal: str) -> RunSnapshot:
        """Start a run and execute it up to the approval breakpoint (or the end)."""
        thread_id = uuid4().hex
        self._threads.add(thread_id)
        bind_context(thread_id=thread_id)
        try:
            initial: AgentState = {
                "candidate": candidate,
                "goal": goal,
                "status": RunStatus.PENDING,
            }
            logger.info("run.start", goal=goal, candidate=candidate.full_name)
            await self.graph.ainvoke(initial, self._config(thread_id))
            snapshot = await self._snapshot(thread_id)
            logger.info(
                "run.paused" if snapshot.awaiting_approval else "run.finished",
                status=snapshot.status.value,
            )
            return snapshot
        finally:
            clear_context()

    async def get_run(self, thread_id: str) -> RunSnapshot | None:
        """Return the current snapshot for a run, or ``None`` if unknown."""
        snapshot = await self._snapshot(thread_id)
        if not snapshot.values.get("candidate"):
            return None
        return snapshot

    async def approve(self, thread_id: str, decision: ApprovalDecision) -> RunSnapshot:
        """Apply a human decision and resume the run to completion."""
        bind_context(thread_id=thread_id)
        try:
            snapshot = await self._snapshot(thread_id)
            if not snapshot.values.get("candidate"):
                raise OrchestratorError(f"Unknown run: {thread_id}")
            if not snapshot.awaiting_approval:
                raise OrchestratorError(
                    f"Run {thread_id} is not awaiting approval (status: {snapshot.status.value})."
                )

            logger.info("run.decision", approved=decision.approved)
            config = self._config(thread_id)
            await self.graph.aupdate_state(config, {"approval": decision})
            await self.graph.ainvoke(None, config)

            snapshot = await self._snapshot(thread_id)
            logger.info("run.resumed", status=snapshot.status.value)
            return snapshot
        finally:
            clear_context()

    async def _snapshot(self, thread_id: str) -> RunSnapshot:
        state = await self.graph.aget_state(self._config(thread_id))
        return RunSnapshot(
            thread_id=thread_id,
            values=cast(AgentState, state.values or {}),
            next=tuple(state.next or ()),
        )
