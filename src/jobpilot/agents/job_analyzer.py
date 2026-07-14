"""Job Analyzer agent — scores a posting against the candidate."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from jobpilot.agents.base import BaseAgent
from jobpilot.agents.prompts import ANALYZER_SYSTEM, build_analyzer_user
from jobpilot.schemas.candidate import CandidateProfile
from jobpilot.schemas.documents import JobAnalysis, Recommendation
from jobpilot.schemas.job import Job
from jobpilot.schemas.state import AgentState, RunStatus, log

_REQUIREMENT_HINTS = ("require", "must", "experience", "years", "strong", "proficient", "familiar")


class _AnalysisOutput(BaseModel):
    match_score: float = Field(ge=0, le=100)
    recommendation: Recommendation = Recommendation.MAYBE
    summary: str = ""
    key_requirements: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class JobAnalyzerAgent(BaseAgent):
    name = "job_analyzer"

    async def run(self, state: AgentState) -> dict:
        job = state.get("selected_job")
        candidate = state["candidate"]
        if job is None:
            return {"status": RunStatus.NO_JOBS}

        if self.use_llm:
            try:
                out = await self._structured(
                    _AnalysisOutput, ANALYZER_SYSTEM, build_analyzer_user(candidate, job)
                )
                analysis = JobAnalysis(job_id=job.id, **out.model_dump())
                return self._result(analysis, source="llm")
            except Exception as exc:
                self.logger.warning("analyzer.llm_failed", error=str(exc))

        return self._result(self._heuristic(candidate, job), source="heuristic")

    def _result(self, analysis: JobAnalysis, source: str) -> dict:
        return {
            "analysis": analysis,
            "status": RunStatus.ANALYZING,
            "logs": log(
                self.name,
                f"Match score {analysis.match_score:.0f}/100 "
                f"({analysis.recommendation.value}, {source}).",
            ),
        }

    def _heuristic(self, candidate: CandidateProfile, job: Job) -> JobAnalysis:
        job_text = f"{job.title} {job.description} {' '.join(job.tags)}".lower()
        cand_skills_l = {s.lower() for s in candidate.skills}
        cand_text = (
            f"{candidate.headline or ''} {candidate.summary or ''} "
            f"{' '.join(candidate.skills)} "
            + " ".join(h for e in candidate.experiences for h in e.highlights)
        ).lower()

        job_tags = [t.lower() for t in job.tags] or self._infer_tags(job_text, cand_skills_l)
        matched_tags = [t for t in job_tags if t in cand_skills_l or t in cand_text]
        missing_tags = [t for t in job_tags if t not in matched_tags]

        matched_skills = [s for s in candidate.skills if s.lower() in job_text]

        base = 100 * len(matched_tags) / len(job_tags) if job_tags else 50.0
        title_l = job.title.lower()
        title_bonus = (
            10
            if any(w in title_l for w in (candidate.headline or "").lower().split())
            or any(r.lower() in title_l for r in candidate.desired_roles)
            else 0
        )
        score = min(100.0, round(base * 0.9 + title_bonus, 1))

        if score >= 70:
            rec = Recommendation.APPLY
        elif score >= 45:
            rec = Recommendation.MAYBE
        else:
            rec = Recommendation.SKIP

        requirements = self._extract_requirements(job.description)
        summary = (
            f"{candidate.full_name} matches {len(matched_tags)}/{len(job_tags)} of the "
            f"key skills for {job.title} at {job.company}. "
            + (f"Strong on {', '.join(matched_skills[:3])}. " if matched_skills else "")
            + (f"Gaps: {', '.join(missing_tags[:3])}." if missing_tags else "No major gaps.")
        )

        return JobAnalysis(
            job_id=job.id,
            match_score=score,
            recommendation=rec,
            summary=summary,
            key_requirements=requirements,
            matched_skills=matched_skills[:12],
            missing_skills=missing_tags[:12],
            keywords=(job.tags or job_tags)[:12],
            strengths=[f"Experience with {s}" for s in matched_skills[:5]],
            gaps=[f"Limited signal on {t}" for t in missing_tags[:5]],
        )

    @staticmethod
    def _infer_tags(job_text: str, cand_skills: set[str]) -> list[str]:
        return [s for s in cand_skills if s in job_text]

    @staticmethod
    def _extract_requirements(description: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+|\n+", description)
        reqs = [
            s.strip(" -•\t")
            for s in sentences
            if any(h in s.lower() for h in _REQUIREMENT_HINTS) and len(s.strip()) > 12
        ]
        return reqs[:6]
