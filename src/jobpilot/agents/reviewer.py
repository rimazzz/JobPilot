"""Reviewer agent — the automated quality gate before human approval."""

from __future__ import annotations

from jobpilot.agents.base import BaseAgent
from jobpilot.agents.prompts import REVIEWER_SYSTEM, build_reviewer_user
from jobpilot.schemas.application import ApplicationResult, Review, ReviewItem, ReviewVerdict
from jobpilot.schemas.documents import CoverLetter, JobAnalysis, TailoredResume
from jobpilot.schemas.job import Job
from jobpilot.schemas.state import AgentState, RunStatus, log


def summarise_form(application: ApplicationResult | None) -> str:
    """Render a filled form as a compact text block for prompts/heuristics."""
    if application is None or application.form is None:
        return "(no form)"
    lines = []
    for field in application.form.fields:
        status = "filled" if field.filled else ("REQUIRED-EMPTY" if field.required else "empty")
        value = (field.value or "").splitlines()[0][:80] if field.value else ""
        lines.append(f"- {field.label or field.name}: {value} [{status}]")
    return "\n".join(lines)


class ReviewerAgent(BaseAgent):
    name = "reviewer"

    async def run(self, state: AgentState) -> dict:
        job = state.get("selected_job")
        analysis = state.get("analysis")
        resume = state.get("resume")
        cover = state.get("cover_letter")
        application = state.get("application")

        if not (job and analysis and resume and cover):
            return {"status": RunStatus.AWAITING_APPROVAL}

        if self.use_llm:
            try:
                review = await self._structured(
                    Review,
                    REVIEWER_SYSTEM,
                    build_reviewer_user(job, analysis, resume, cover, summarise_form(application)),
                )
                return self._result(review, source="llm")
            except Exception as exc:
                self.logger.warning("reviewer.llm_failed", error=str(exc))

        return self._result(
            self._heuristic(job, analysis, resume, cover, application), source="heuristic"
        )

    def _result(self, review: Review, source: str) -> dict:
        return {
            "review": review,
            "status": RunStatus.AWAITING_APPROVAL,
            "logs": log(
                self.name,
                f"Review complete: {review.verdict.value} "
                f"(score {review.score:.0f}/100, {source}). Awaiting human approval.",
            ),
        }

    def _heuristic(
        self,
        job: Job,
        analysis: JobAnalysis,
        resume: TailoredResume,
        cover: CoverLetter,
        application: ApplicationResult | None,
    ) -> Review:
        form = application.form if application else None
        matched_in_resume = set(resume.highlighted_skills) & set(analysis.matched_skills)
        company_mentioned = job.company.lower() in cover.text.lower()
        required_ok = form is not None and not form.unfilled_required
        email_ok = form is not None and any(
            f.filled and (f.field_type.value == "email" or "email" in (f.label or "").lower())
            for f in form.fields
        )
        match_ok = analysis.match_score >= 50

        checklist = [
            ReviewItem(
                name="Resume tailored to role",
                passed=bool(resume.changes or matched_in_resume),
                comment="Skills reprioritised and summary aligned."
                if resume.changes
                else "No explicit tailoring detected.",
            ),
            ReviewItem(
                name="Cover letter references company",
                passed=company_mentioned,
                comment="Mentions the company by name."
                if company_mentioned
                else f"Does not mention {job.company}.",
            ),
            ReviewItem(
                name="Required fields answered",
                passed=required_ok,
                comment="All required fields filled."
                if required_ok
                else "Some required fields need human input.",
            ),
            ReviewItem(
                name="Contact info present",
                passed=email_ok,
                comment="Email supplied." if email_ok else "Email field not detected/filled.",
            ),
            ReviewItem(
                name="Reasonable match score",
                passed=match_ok,
                comment=f"Match score {analysis.match_score:.0f}/100.",
            ),
        ]

        passed = sum(1 for item in checklist if item.passed)
        score = round(0.5 * analysis.match_score + 0.5 * 100 * passed / len(checklist), 1)
        issues = [item.comment for item in checklist if not item.passed]

        if score < 35 or not required_ok and analysis.match_score < 40:
            verdict = ReviewVerdict.REJECT
        elif issues:
            verdict = ReviewVerdict.REVISE
        else:
            verdict = ReviewVerdict.APPROVE

        suggestions: list[str] = []
        if not required_ok and form is not None:
            missing = ", ".join(f.label or f.name or "?" for f in form.unfilled_required)
            suggestions.append(f"Complete required fields before submitting: {missing}.")
        if not company_mentioned:
            suggestions.append("Personalise the cover letter with a company-specific detail.")
        if analysis.missing_skills:
            suggestions.append(
                f"Address gaps if possible: {', '.join(analysis.missing_skills[:3])}."
            )

        return Review(
            verdict=verdict,
            score=score,
            summary=(
                f"{passed}/{len(checklist)} checks passed; match score "
                f"{analysis.match_score:.0f}. Recommended action: {verdict.value}."
            ),
            checklist=checklist,
            issues=issues,
            suggestions=suggestions,
        )
