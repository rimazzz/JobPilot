"""Resume agent — produces a resume tailored to the selected job."""

from __future__ import annotations

from pydantic import BaseModel, Field

from jobpilot.agents.base import BaseAgent
from jobpilot.agents.prompts import RESUME_SYSTEM, build_resume_user
from jobpilot.schemas.candidate import CandidateProfile
from jobpilot.schemas.documents import JobAnalysis, TailoredResume
from jobpilot.schemas.job import Job
from jobpilot.schemas.state import AgentState, RunStatus, log


class _ResumeOutput(BaseModel):
    headline: str
    summary: str
    highlighted_skills: list[str] = Field(default_factory=list)
    emphasized_experience: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)


def render_resume_markdown(
    candidate: CandidateProfile,
    headline: str,
    summary: str,
    skills: list[str],
    highlights: list[str],
) -> str:
    """Render a clean Markdown resume from structured pieces.

    The candidate's real experience and education are always rendered verbatim;
    only the headline, summary, skill ordering and the "key highlights" section
    are tailored, which keeps the document truthful.
    """
    contact_bits = [candidate.email, candidate.phone, candidate.location]
    contact_bits += [f"{k}: {v}" for k, v in candidate.links.items()]
    contact = " | ".join(b for b in contact_bits if b)

    lines = [f"# {candidate.full_name}", f"*{headline}*", "", contact, "", "## Summary", summary]

    if highlights:
        lines += ["", "## Key Highlights for this Role"]
        lines += [f"- {h}" for h in highlights]

    if skills:
        lines += ["", "## Skills", ", ".join(skills)]

    if candidate.experiences:
        lines += ["", "## Experience"]
        for exp in candidate.experiences:
            period = f"{exp.start_date or '?'} – {exp.end_date or 'Present'}"
            loc = f", {exp.location}" if exp.location else ""
            lines.append(f"### {exp.title} — {exp.company}{loc} ({period})")
            lines += [f"- {hl}" for hl in exp.highlights]

    if candidate.education:
        lines += ["", "## Education"]
        for edu in candidate.education:
            degree = " ".join(filter(None, [edu.degree, edu.field_of_study]))
            year = f" ({edu.graduation_year})" if edu.graduation_year else ""
            lines.append(f"- {degree} — {edu.institution}{year}".replace("  ", " "))

    return "\n".join(lines).strip() + "\n"


class ResumeAgent(BaseAgent):
    name = "resume"

    async def run(self, state: AgentState) -> dict:
        job = state.get("selected_job")
        analysis = state.get("analysis")
        candidate = state["candidate"]
        if job is None or analysis is None:
            return {"status": RunStatus.DRAFTING}

        if self.use_llm:
            try:
                out = await self._structured(
                    _ResumeOutput, RESUME_SYSTEM, build_resume_user(candidate, job, analysis)
                )
                skills = out.highlighted_skills or self._order_skills(candidate, analysis)
                resume = TailoredResume(
                    job_id=job.id,
                    headline=out.headline,
                    summary=out.summary,
                    highlighted_skills=skills,
                    emphasized_experience=out.emphasized_experience,
                    markdown=render_resume_markdown(
                        candidate, out.headline, out.summary, skills, out.emphasized_experience
                    ),
                    changes=out.changes,
                )
                return self._result(resume, source="llm")
            except Exception as exc:
                self.logger.warning("resume.llm_failed", error=str(exc))

        return self._result(self._heuristic(candidate, job, analysis), source="heuristic")

    def _result(self, resume: TailoredResume, source: str) -> dict:
        return {
            "resume": resume,
            "status": RunStatus.DRAFTING,
            "logs": log(self.name, f"Tailored resume drafted ({source})."),
        }

    @staticmethod
    def _order_skills(candidate: CandidateProfile, analysis: JobAnalysis) -> list[str]:
        matched = [s for s in candidate.skills if s in analysis.matched_skills]
        rest = [s for s in candidate.skills if s not in analysis.matched_skills]
        return matched + rest

    def _heuristic(
        self, candidate: CandidateProfile, job: Job, analysis: JobAnalysis
    ) -> TailoredResume:
        headline = candidate.headline or job.title
        summary = candidate.summary or (
            f"{headline} with experience in {', '.join(candidate.skills[:4])}. "
            f"Targeting the {job.title} role at {job.company}."
        )
        skills = self._order_skills(candidate, analysis)

        # Emphasise real highlights that mention a matched skill.
        matched_l = {s.lower() for s in analysis.matched_skills}
        highlights = [
            hl
            for exp in candidate.experiences
            for hl in exp.highlights
            if any(m in hl.lower() for m in matched_l)
        ][:6]
        if not highlights:
            highlights = [hl for exp in candidate.experiences for hl in exp.highlights][:4]

        changes = [
            f"Reordered skills to lead with role-relevant: {', '.join(skills[:4])}.",
            f"Summary aligned to the {job.title} role at {job.company}.",
        ]
        if highlights:
            changes.append("Surfaced achievements matching the job's key skills.")

        return TailoredResume(
            job_id=job.id,
            headline=headline,
            summary=summary,
            highlighted_skills=skills,
            emphasized_experience=highlights,
            markdown=render_resume_markdown(candidate, headline, summary, skills, highlights),
            changes=changes,
        )
