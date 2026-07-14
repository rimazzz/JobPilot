"""Tests for the run lifecycle orchestrator."""

from __future__ import annotations

import pytest

from jobpilot.orchestrator import OrchestratorError
from jobpilot.schemas.application import ApprovalDecision


async def test_get_unknown_run_returns_none(orchestrator):
    assert await orchestrator.get_run("does-not-exist") is None


async def test_approve_unknown_run_raises(orchestrator):
    with pytest.raises(OrchestratorError, match="Unknown run"):
        await orchestrator.approve("nope", ApprovalDecision(approved=True))


async def test_cannot_approve_when_not_awaiting(orchestrator, candidate):
    snap = await orchestrator.start_run(candidate, "Senior Python engineer")
    await orchestrator.approve(snap.thread_id, ApprovalDecision(approved=True))
    # Second approval should fail — the run already completed.
    with pytest.raises(OrchestratorError, match="not awaiting approval"):
        await orchestrator.approve(snap.thread_id, ApprovalDecision(approved=True))


async def test_get_run_after_start(orchestrator, candidate):
    snap = await orchestrator.start_run(candidate, "Senior Python engineer")
    fetched = await orchestrator.get_run(snap.thread_id)
    assert fetched is not None
    assert fetched.thread_id == snap.thread_id
    assert fetched.awaiting_approval
