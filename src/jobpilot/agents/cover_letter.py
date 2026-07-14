"""Cover Letter agent — drafts a tailored cover letter."""

from __future__ import annotations

from pydantic import BaseModel

from jobpilot.agents.base import BaseAgent
from jobpilot.agents.prompts import COVER_LETTER_SYSTEM, build_cover_letter_user
from jobpilot.schemas.candidate import CandidateProfile
from jobpilot.schemas.documents import CoverLetter, JobAnalysis
from jobpilot.schemas.job import Job
from jobpilot.schemas.state import AgentState, RunStatus, log


class _CoverLetterOutput(BaseModel):
    greeting: str = "Dear Hiring Manager,"
    body: str
    closing: str = "Sincerely,"


class CoverLetterAgent(BaseAgent):
    name = "cover_letter"

    async def run(self, state: AgentState) -> dict:
        job = state.get("selected_job")
        analysis = state.get("analysis")
        candidate = state["candidate"]
        if job is None or analysis is None:
            return {"status": RunStatus.DRAFTING}

        if self.use_llm:
            try:
                out = await self._structured(
                    _CoverLetterOutput,
                    COVER_LETTER_SYSTEM,
                    build_cover_letter_user(candidate, job, analysis),
                )
                letter = CoverLetter(
                    job_id=job.id,
                    greeting=out.greeting,
                    body=out.body,
                    closing=out.closing,
                    signature=candidate.full_name,
                )
                return self._result(letter, source="llm")
            except Exception as exc:
                self.logger.warning("cover_letter.llm_failed", error=str(exc))

        return self._result(self._heuristic(candidate, job, analysis), source="heuristic")

    def _result(self, letter: CoverLetter, source: str) -> dict:
        return {
            "cover_letter": letter,
            "status": RunStatus.DRAFTING,
            "logs": log(self.name, f"Cover letter drafted ({source}, {letter.word_count} words)."),
        }

    def _heuristic(
        self, candidate: CandidateProfile, job: Job, analysis: JobAnalysis
    ) -> CoverLetter:
        skills = ", ".join(analysis.matched_skills[:3]) or ", ".join(candidate.skills[:3])
        strength = (
            analysis.strengths[0] if analysis.strengths else "a strong engineering track record"
        )
        exp_line = ""
        if candidate.experiences:
            top = candidate.experiences[0]
            exp_line = (
                f" In my role as {top.title} at {top.company}, I delivered work that maps "
                f"directly to what your team needs."
            )

        body = (
            f"I am excited to apply for the {job.title} position at {job.company}. "
            f"The role is a strong match for my background{': ' + strength if strength else ''}, "
            f"and I am drawn to the opportunity to contribute from day one.\n\n"
            f"My experience with {skills} lines up closely with the requirements you have "
            f"outlined.{exp_line} I focus on shipping reliable, well-tested software and "
            f"collaborating closely with teammates to move quickly without cutting corners.\n\n"
            f"I would welcome the chance to discuss how I can help {job.company} reach its "
            f"goals. Thank you for your time and consideration."
        )
        return CoverLetter(job_id=job.id, body=body, signature=candidate.full_name)
