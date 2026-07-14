"""Tests for the individual agents (heuristic + LLM paths)."""

from __future__ import annotations

from jobpilot.agents.cover_letter import CoverLetterAgent
from jobpilot.agents.job_analyzer import JobAnalyzerAgent, _AnalysisOutput
from jobpilot.agents.planner import PlannerAgent, _PlannerOutput
from jobpilot.agents.resume import ResumeAgent
from jobpilot.agents.reviewer import ReviewerAgent
from jobpilot.agents.summarizer import SummarizerAgent
from jobpilot.schemas.application import ApplicationForm, ApplicationResult, ApplicationStatus
from jobpilot.schemas.documents import Recommendation
from jobpilot.schemas.state import RunStatus
from tests.conftest import FakeChatModel

# -- Planner -----------------------------------------------------------------


async def test_planner_heuristic(settings, candidate):
    out = await PlannerAgent(settings).run({"candidate": candidate, "goal": "remote python"})
    assert out["plan"].target_role
    assert "python" in out["query"].keywords.lower()
    assert out["query"].remote is True  # goal + open_to_remote
    assert out["status"] == RunStatus.PLANNING


async def test_planner_llm(settings, candidate):
    fake = FakeChatModel(
        structured=_PlannerOutput(
            target_role="Staff Engineer",
            keywords="python distributed systems",
            objective="Land a staff role",
            steps=["search", "analyze"],
        )
    )
    out = await PlannerAgent(settings, llm=fake).run({"candidate": candidate, "goal": "x"})
    assert out["plan"].target_role == "Staff Engineer"
    assert out["query"].keywords == "python distributed systems"


# -- Job Analyzer ------------------------------------------------------------


async def test_analyzer_heuristic(settings, candidate, job):
    out = await JobAnalyzerAgent(settings).run({"candidate": candidate, "selected_job": job})
    analysis = out["analysis"]
    assert analysis.job_id == job.id
    assert 0 <= analysis.match_score <= 100
    assert analysis.recommendation in set(Recommendation)
    assert "Python" in analysis.matched_skills


async def test_analyzer_llm_falls_back_on_error(settings, candidate, job):
    fake = FakeChatModel(error=RuntimeError("api down"))
    out = await JobAnalyzerAgent(settings, llm=fake).run(
        {"candidate": candidate, "selected_job": job}
    )
    # Falls back to heuristic rather than raising.
    assert out["analysis"].job_id == job.id


async def test_analyzer_llm_success(settings, candidate, job):
    fake = FakeChatModel(
        structured=_AnalysisOutput(
            match_score=91, recommendation=Recommendation.APPLY, summary="great"
        )
    )
    out = await JobAnalyzerAgent(settings, llm=fake).run(
        {"candidate": candidate, "selected_job": job}
    )
    assert out["analysis"].match_score == 91
    assert out["analysis"].recommendation == Recommendation.APPLY


# -- Resume ------------------------------------------------------------------


async def test_resume_heuristic(settings, candidate, job, analysis):
    out = await ResumeAgent(settings).run(
        {"candidate": candidate, "selected_job": job, "analysis": analysis}
    )
    resume = out["resume"]
    assert candidate.full_name in resume.markdown
    assert "## Skills" in resume.markdown
    assert resume.changes  # tailoring notes present
    # Matched skills lead the ordered skill list.
    assert resume.highlighted_skills[0] in analysis.matched_skills


# -- Cover Letter ------------------------------------------------------------


async def test_cover_letter_heuristic(settings, candidate, job, analysis):
    out = await CoverLetterAgent(settings).run(
        {"candidate": candidate, "selected_job": job, "analysis": analysis}
    )
    letter = out["cover_letter"]
    assert job.company in letter.text
    assert letter.signature == candidate.full_name
    assert letter.word_count > 20


# -- Reviewer ----------------------------------------------------------------


def _filled_form_result(job) -> ApplicationResult:
    from jobpilot.schemas.application import FormField

    # Build a filled form synchronously via the simulated standard form spec.
    from jobpilot.tools.browser import (  # local import
        _STANDARD_FORM,
        ApplicationContext,
        map_fields,
    )

    ctx = ApplicationContext(
        full_name="Ada Lovelace",
        email="ada@example.com",
        phone="1",
        resume_path="/tmp/r.md",
        cover_letter_text="hi",
    )
    fields = map_fields([FormField(**spec) for spec in _STANDARD_FORM], ctx)
    for f in fields:
        f.filled = f.value is not None
    return ApplicationResult(
        job_id=job.id,
        status=ApplicationStatus.FILLED,
        form=ApplicationForm(url=job.application_url, detected=True, fields=fields),
    )


async def test_reviewer_heuristic(settings, job, analysis, candidate):
    from jobpilot.agents.cover_letter import CoverLetterAgent
    from jobpilot.agents.resume import ResumeAgent

    resume = (
        await ResumeAgent(settings).run(
            {"candidate": candidate, "selected_job": job, "analysis": analysis}
        )
    )["resume"]
    cover = (
        await CoverLetterAgent(settings).run(
            {"candidate": candidate, "selected_job": job, "analysis": analysis}
        )
    )["cover_letter"]

    out = await ReviewerAgent(settings).run(
        {
            "selected_job": job,
            "analysis": analysis,
            "resume": resume,
            "cover_letter": cover,
            "application": _filled_form_result(job),
        }
    )
    review = out["review"]
    assert out["status"] == RunStatus.AWAITING_APPROVAL
    assert len(review.checklist) == 5
    assert review.verdict.value in {"approve", "revise", "reject"}


# -- Summarizer --------------------------------------------------------------


async def test_summarizer_heuristic(settings, candidate, job, analysis):
    out = await SummarizerAgent(settings).run(
        {"candidate": candidate, "selected_job": job, "analysis": analysis}
    )
    assert out["summary"]
    assert out["status"] in set(RunStatus)


async def test_summarizer_llm_text(settings, candidate, job):
    fake = FakeChatModel(text="Here is your briefing.")
    out = await SummarizerAgent(settings, llm=fake).run(
        {"candidate": candidate, "selected_job": job}
    )
    assert out["summary"] == "Here is your briefing."


async def test_summarizer_no_jobs(settings, candidate):
    out = await SummarizerAgent(settings).run({"candidate": candidate})
    assert out["status"] == RunStatus.NO_JOBS
