"""Request and response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from jobpilot.orchestrator import RunSnapshot
from jobpilot.schemas.application import ApplicationResult, Review
from jobpilot.schemas.candidate import CandidateProfile
from jobpilot.schemas.documents import CoverLetter, JobAnalysis, TailoredResume
from jobpilot.schemas.job import Job
from jobpilot.schemas.state import AgentLog, Plan, RunStatus


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    llm_provider: str
    llm_model: str
    llm_enabled: bool = Field(description="True when an API key is configured.")
    search_provider: str
    browser_mode: str


class StartRunRequest(BaseModel):
    """Body for starting a new application run."""

    candidate: CandidateProfile
    goal: str = Field(min_length=1, description="Free-text description of the target job.")


class ApproveRequest(BaseModel):
    """Body for approving or rejecting a paused run."""

    approved: bool
    notes: str | None = None
    field_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Optional per-field value overrides keyed by the form field selector.",
    )


class RunResponse(BaseModel):
    """A full view of a run's current state."""

    thread_id: str
    status: RunStatus
    awaiting_approval: bool
    plan: Plan | None = None
    job: Job | None = None
    analysis: JobAnalysis | None = None
    resume: TailoredResume | None = None
    cover_letter: CoverLetter | None = None
    cover_letter_text: str | None = None
    application: ApplicationResult | None = None
    review: Review | None = None
    summary: str | None = None
    logs: list[AgentLog] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @classmethod
    def from_snapshot(cls, snapshot: RunSnapshot) -> RunResponse:
        values = snapshot.values
        cover = values.get("cover_letter")
        return cls(
            thread_id=snapshot.thread_id,
            status=snapshot.status,
            awaiting_approval=snapshot.awaiting_approval,
            plan=values.get("plan"),
            job=values.get("selected_job"),
            analysis=values.get("analysis"),
            resume=values.get("resume"),
            cover_letter=cover,
            cover_letter_text=cover.text if cover else None,
            application=values.get("application"),
            review=values.get("review"),
            summary=values.get("summary"),
            logs=list(values.get("logs", [])),
            errors=list(values.get("errors", [])),
        )
