"""End-to-end tests for the compiled LangGraph workflow."""

from __future__ import annotations

from jobpilot.graph import build_graph
from jobpilot.schemas.state import RunStatus
from jobpilot.tools.job_search import JobSearchProvider


class _EmptyProvider(JobSearchProvider):
    name = "empty"

    async def search(self, query):
        return []


async def test_full_run_reaches_approval_then_completes(orchestrator, candidate):
    snap = await orchestrator.start_run(candidate, "Senior Python engineer, remote")
    assert snap.awaiting_approval
    assert snap.status == RunStatus.AWAITING_APPROVAL
    assert snap.values["selected_job"] is not None
    assert snap.values["resume"] is not None
    assert snap.values["cover_letter"] is not None
    assert snap.values["application"].form is not None

    from jobpilot.schemas.application import ApprovalDecision

    done = await orchestrator.approve(snap.thread_id, ApprovalDecision(approved=True))
    assert done.status == RunStatus.COMPLETED
    assert done.values["application"].submitted is True
    assert done.values["summary"]


async def test_reject_path(orchestrator, candidate):
    from jobpilot.schemas.application import ApprovalDecision

    snap = await orchestrator.start_run(candidate, "ML engineer")
    done = await orchestrator.approve(snap.thread_id, ApprovalDecision(approved=False))
    assert done.status == RunStatus.REJECTED
    assert done.values["application"].submitted is False


async def test_no_jobs_short_circuits(settings, candidate):
    graph = build_graph(settings, search_provider=_EmptyProvider())
    config = {"configurable": {"thread_id": "no-jobs"}}
    state = await graph.ainvoke(
        {"candidate": candidate, "goal": "unicorn wrangler", "status": RunStatus.PENDING},
        config,
    )
    assert state["status"] == RunStatus.NO_JOBS
    assert state["summary"]
    # The run finished (no pending approval node).
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ()


async def test_submit_disabled_by_setting(candidate, settings):
    from jobpilot.orchestrator import Orchestrator
    from jobpilot.schemas.application import ApprovalDecision

    no_submit = settings.model_copy(update={"browser_allow_submit": False})
    orch = Orchestrator(settings=no_submit)
    snap = await orch.start_run(candidate, "Senior Python engineer")
    done = await orch.approve(snap.thread_id, ApprovalDecision(approved=True))
    # Approved, but submission was disabled -> not submitted, run completes.
    assert done.values["application"].submitted is False
    assert done.status == RunStatus.COMPLETED
