"""The LangGraph run state and its supporting models.

The graph state is a :class:`typing.TypedDict` (the idiomatic LangGraph shape),
while the nested domain objects are rich Pydantic models. List fields that every
node contributes to (``logs``, ``errors``) use ``operator.add`` reducers so
updates append rather than overwrite.
"""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from jobpilot.schemas.application import ApplicationResult, ApprovalDecision, Review
from jobpilot.schemas.candidate import CandidateProfile
from jobpilot.schemas.documents import CoverLetter, JobAnalysis, TailoredResume
from jobpilot.schemas.job import Job, JobSearchQuery


class RunStatus(StrEnum):
    """High-level status of a run, surfaced through the API."""

    PENDING = "pending"
    PLANNING = "planning"
    SEARCHING = "searching"
    ANALYZING = "analyzing"
    DRAFTING = "drafting"
    FILLING = "filling"
    AWAITING_APPROVAL = "awaiting_approval"
    SUBMITTING = "submitting"
    COMPLETED = "completed"
    NO_JOBS = "no_jobs"
    REJECTED = "rejected"
    FAILED = "failed"


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str


class Plan(BaseModel):
    """The Planner agent's strategy for a run."""

    model_config = ConfigDict(extra="forbid")

    objective: str
    target_role: str
    steps: list[PlanStep] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AgentLog(BaseModel):
    """A structured, timeline-ordered log entry produced by an agent."""

    model_config = ConfigDict(extra="forbid")

    agent: str
    message: str
    level: str = "info"
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


def log(agent: str, message: str, level: str = "info") -> list[AgentLog]:
    """Build a single-element log list for a node's state update."""
    return [AgentLog(agent=agent, message=message, level=level)]


class AgentState(TypedDict, total=False):
    """The shared state threaded through the LangGraph workflow.

    ``total=False`` so nodes may return partial updates. LangGraph merges each
    node's returned dict into the running state.
    """

    # --- Inputs ---
    candidate: CandidateProfile
    goal: str

    # --- Planning ---
    plan: Plan
    query: JobSearchQuery

    # --- Search ---
    jobs: list[Job]
    selected_job: Job | None

    # --- Analysis ---
    analysis: JobAnalysis | None

    # --- Drafted documents ---
    resume: TailoredResume | None
    cover_letter: CoverLetter | None

    # --- Application + human-in-the-loop ---
    application: ApplicationResult | None
    review: Review | None
    approval: ApprovalDecision | None

    # --- Output / bookkeeping ---
    summary: str | None
    status: RunStatus
    logs: Annotated[list[AgentLog], operator.add]
    errors: Annotated[list[str], operator.add]
