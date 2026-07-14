"""Pydantic domain models and the LangGraph run state."""

from __future__ import annotations

from jobpilot.schemas.application import (
    ApplicationForm,
    ApplicationResult,
    ApplicationStatus,
    ApprovalDecision,
    FieldType,
    FormField,
    Review,
    ReviewItem,
    ReviewVerdict,
)
from jobpilot.schemas.candidate import CandidateProfile, Education, Experience
from jobpilot.schemas.documents import (
    CoverLetter,
    JobAnalysis,
    Recommendation,
    TailoredResume,
)
from jobpilot.schemas.job import Job, JobSearchQuery
from jobpilot.schemas.state import (
    AgentLog,
    AgentState,
    Plan,
    PlanStep,
    RunStatus,
    log,
)

__all__ = [
    # candidate
    "CandidateProfile",
    "Experience",
    "Education",
    # job
    "Job",
    "JobSearchQuery",
    # documents
    "JobAnalysis",
    "Recommendation",
    "TailoredResume",
    "CoverLetter",
    # application
    "ApplicationForm",
    "ApplicationResult",
    "ApplicationStatus",
    "ApprovalDecision",
    "FieldType",
    "FormField",
    "Review",
    "ReviewItem",
    "ReviewVerdict",
    # state
    "AgentState",
    "AgentLog",
    "Plan",
    "PlanStep",
    "RunStatus",
    "log",
]
