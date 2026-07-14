"""Summarizer agent — the terminal node that briefs the candidate."""

from __future__ import annotations

from jobpilot.agents.base import BaseAgent
from jobpilot.agents.prompts import SUMMARIZER_SYSTEM, build_summarizer_user
from jobpilot.schemas.application import ApplicationStatus
from jobpilot.schemas.state import AgentState, RunStatus, log


class SummarizerAgent(BaseAgent):
    name = "summarizer"

    async def run(self, state: AgentState) -> dict:
        final_status = self._final_status(state)
        context = self._context(state, final_status)

        summary: str | None = None
        source = "heuristic"
        if self.use_llm:
            try:
                summary = await self._text(SUMMARIZER_SYSTEM, build_summarizer_user(context))
                source = "llm"
            except Exception as exc:
                self.logger.warning("summarizer.llm_failed", error=str(exc))

        if summary is None:
            summary = self._heuristic(state, final_status)

        return {
            "summary": summary,
            "status": final_status,
            "logs": log(
                self.name, f"Run summarised ({source}); final status: {final_status.value}."
            ),
        }

    @staticmethod
    def _final_status(state: AgentState) -> RunStatus:
        job = state.get("selected_job")
        application = state.get("application")
        approval = state.get("approval")

        if job is None:
            return RunStatus.NO_JOBS
        if application is not None:
            if application.status == ApplicationStatus.SUBMITTED:
                return RunStatus.COMPLETED
            if application.status == ApplicationStatus.FAILED:
                return RunStatus.FAILED
        if approval is not None and not approval.approved:
            return RunStatus.REJECTED
        return RunStatus.COMPLETED

    @staticmethod
    def _context(state: AgentState, final_status: RunStatus) -> str:
        job = state.get("selected_job")
        analysis = state.get("analysis")
        resume = state.get("resume")
        cover = state.get("cover_letter")
        application = state.get("application")
        review = state.get("review")
        approval = state.get("approval")

        parts = [f"Final status: {final_status.value}"]
        if job:
            parts.append(f"Job: {job.title} @ {job.company} ({job.location or 'n/a'})")
        if analysis:
            parts.append(
                f"Match: {analysis.match_score:.0f}/100 ({analysis.recommendation.value}); "
                f"gaps: {', '.join(analysis.missing_skills[:3]) or 'none'}"
            )
        if resume:
            parts.append(f"Resume changes: {'; '.join(resume.changes[:3]) or 'n/a'}")
        if cover:
            parts.append(f"Cover letter: {cover.word_count} words")
        if application and application.form:
            parts.append(
                f"Form: {len(application.form.filled_fields)}/"
                f"{len(application.form.fields)} fields filled; status {application.status.value}"
            )
        if review:
            parts.append(f"Reviewer verdict: {review.verdict.value} (score {review.score:.0f})")
        if approval is not None:
            parts.append(f"Human decision: {'approved' if approval.approved else 'rejected'}")
        return "\n".join(parts)

    def _heuristic(self, state: AgentState, final_status: RunStatus) -> str:
        job = state.get("selected_job")
        analysis = state.get("analysis")
        application = state.get("application")

        if job is None:
            return (
                "No matching jobs were found for your search. Try broadening the "
                "keywords or location and run again."
            )

        head = f"Target role: {job.title} at {job.company}."
        match = (
            f" It scored {analysis.match_score:.0f}/100 against your profile." if analysis else ""
        )

        if final_status == RunStatus.COMPLETED and application and application.submitted:
            outcome = (
                " Your tailored resume and cover letter were prepared and the "
                "application was submitted after your approval."
            )
            nxt = " Next: watch for a confirmation email and follow up in about a week."
        elif final_status == RunStatus.REJECTED:
            outcome = " You reviewed the drafts and chose not to submit."
            nxt = " Next: adjust the drafts or pick a different role and rerun."
        elif final_status == RunStatus.FAILED:
            outcome = " The application could not be completed automatically."
            nxt = (
                " Next: open the application URL and finish it manually using the "
                "drafted documents."
            )
        else:
            outcome = (
                " Your tailored resume, cover letter and filled form are ready and "
                "awaiting your decision."
            )
            nxt = " Next: review the drafts and approve or reject submission."

        return head + match + outcome + nxt
