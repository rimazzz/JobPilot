"""Checkpoint serialization.

LangGraph checkpoints serialize the run state with msgpack and, for safety,
require custom types to be explicitly allow-listed before they are
deserialized. We register JobPilot's own schema types so pause/resume works
without warnings and without opening the door to arbitrary deserialization.
"""

from __future__ import annotations

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

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
from jobpilot.schemas.documents import CoverLetter, JobAnalysis, Recommendation, TailoredResume
from jobpilot.schemas.job import Job, JobSearchQuery
from jobpilot.schemas.state import AgentLog, Plan, PlanStep, RunStatus

#: Every JobPilot type that can appear in the graph state / a checkpoint.
CHECKPOINT_TYPES = (
    CandidateProfile,
    Experience,
    Education,
    Job,
    JobSearchQuery,
    JobAnalysis,
    Recommendation,
    TailoredResume,
    CoverLetter,
    ApplicationForm,
    FormField,
    FieldType,
    ApplicationResult,
    ApplicationStatus,
    Review,
    ReviewItem,
    ReviewVerdict,
    ApprovalDecision,
    Plan,
    PlanStep,
    AgentLog,
    RunStatus,
)

#: ``(module, qualname)`` pairs in the shape LangGraph's msgpack allowlist wants.
ALLOWED_MSGPACK_MODULES: set[tuple[str, str]] = {
    (cls.__module__, cls.__qualname__) for cls in CHECKPOINT_TYPES
}


def build_serde() -> JsonPlusSerializer:
    """Return a serializer that trusts JobPilot's own schema types."""
    return JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_MSGPACK_MODULES)
