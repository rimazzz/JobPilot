"""HTTP routes for JobPilot."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from jobpilot import __version__
from jobpilot.api.deps import get_orchestrator, get_settings_dep
from jobpilot.api.models import (
    ApproveRequest,
    HealthResponse,
    RunResponse,
    StartRunRequest,
)
from jobpilot.config import Settings
from jobpilot.orchestrator import Orchestrator, OrchestratorError
from jobpilot.schemas.application import ApprovalDecision

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["meta"])
async def health(settings: Settings = Depends(get_settings_dep)) -> HealthResponse:
    """Liveness probe and effective configuration summary."""
    return HealthResponse(
        version=__version__,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        llm_enabled=bool(settings.active_api_key),
        search_provider=settings.search_provider,
        browser_mode=settings.browser_mode,
    )


@router.post(
    "/applications",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["applications"],
)
async def start_application(
    body: StartRunRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> RunResponse:
    """Start a run. Executes up to the human-approval breakpoint (or the end)."""
    snapshot = await orchestrator.start_run(body.candidate, body.goal)
    return RunResponse.from_snapshot(snapshot)


@router.get(
    "/applications/{thread_id}",
    response_model=RunResponse,
    tags=["applications"],
)
async def get_application(
    thread_id: str,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> RunResponse:
    """Fetch the current state of a run."""
    snapshot = await orchestrator.get_run(thread_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown run: {thread_id}")
    return RunResponse.from_snapshot(snapshot)


@router.post(
    "/applications/{thread_id}/approve",
    response_model=RunResponse,
    tags=["applications"],
)
async def approve_application(
    thread_id: str,
    body: ApproveRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> RunResponse:
    """Approve or reject a paused run, then resume it to completion."""
    decision = ApprovalDecision(
        approved=body.approved, notes=body.notes, field_overrides=body.field_overrides
    )
    try:
        snapshot = await orchestrator.approve(thread_id, decision)
    except OrchestratorError as exc:
        message = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if message.startswith("Unknown run")
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(code, message) from exc
    return RunResponse.from_snapshot(snapshot)
