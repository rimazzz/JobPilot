"""Planner agent — turns a candidate + free-text goal into a concrete plan."""

from __future__ import annotations

from pydantic import BaseModel, Field

from jobpilot.agents.base import BaseAgent
from jobpilot.agents.prompts import PLANNER_SYSTEM, build_planner_user
from jobpilot.schemas.job import JobSearchQuery
from jobpilot.schemas.state import AgentState, Plan, PlanStep, RunStatus, log

STANDARD_STEPS: list[tuple[str, str]] = [
    ("search", "Search job boards for relevant openings."),
    ("analyze", "Analyse the best-matching posting against the resume."),
    ("tailor_resume", "Draft a resume tailored to the role."),
    ("cover_letter", "Write a matching cover letter."),
    ("fill_form", "Fill the application form (no submission)."),
    ("review", "Quality-check everything before human approval."),
    ("approval", "Pause for explicit human approval."),
    ("submit", "Submit only if approved."),
    ("summarize", "Summarise the outcome and next steps."),
]

_SENIORITY_TERMS = ("principal", "staff", "lead", "senior", "junior", "entry", "mid")


class _PlannerOutput(BaseModel):
    """Structured planner reply."""

    target_role: str
    keywords: str = Field(description="Space/comma separated search keywords.")
    location: str | None = None
    remote: bool | None = None
    seniority: str | None = None
    objective: str
    steps: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PlannerAgent(BaseAgent):
    name = "planner"

    async def run(self, state: AgentState) -> dict:
        candidate = state["candidate"]
        goal = state.get("goal", "")

        if self.use_llm:
            try:
                out = await self._structured(
                    _PlannerOutput, PLANNER_SYSTEM, build_planner_user(candidate, goal)
                )
                plan = Plan(
                    objective=out.objective,
                    target_role=out.target_role,
                    steps=self._steps(out.steps),
                    notes=out.notes,
                )
                query = JobSearchQuery(
                    keywords=out.keywords or out.target_role,
                    location=out.location,
                    remote=out.remote,
                    seniority=out.seniority,
                    limit=self.settings.max_jobs,
                )
                return self._result(plan, query, source="llm")
            except Exception as exc:  # fall back to heuristic on any LLM failure
                self.logger.warning("planner.llm_failed", error=str(exc))

        plan, query = self._heuristic(candidate, goal)
        return self._result(plan, query, source="heuristic")

    def _result(self, plan: Plan, query: JobSearchQuery, source: str) -> dict:
        return {
            "plan": plan,
            "query": query,
            "status": RunStatus.PLANNING,
            "logs": log(
                self.name,
                f"Planned target role '{plan.target_role}' with keywords "
                f"'{query.keywords}' ({source}).",
            ),
        }

    @staticmethod
    def _steps(names: list[str]) -> list[PlanStep]:
        described = dict(STANDARD_STEPS)
        if not names:
            return [PlanStep(name=n, description=d) for n, d in STANDARD_STEPS]
        return [PlanStep(name=n, description=described.get(n, n)) for n in names]

    def _heuristic(self, candidate, goal: str) -> tuple[Plan, JobSearchQuery]:
        goal_l = goal.lower()

        target_role = (
            (candidate.desired_roles[0] if candidate.desired_roles else None)
            or candidate.headline
            or (goal.strip() if goal.strip() else "Software Engineer")
        )

        keyword_parts: list[str] = []
        keyword_parts += candidate.desired_roles
        if candidate.headline:
            keyword_parts.append(candidate.headline)
        keyword_parts += candidate.skills[:5]
        keyword_parts += [w for w in goal.split() if len(w) > 3]
        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique_parts: list[str] = []
        for part in keyword_parts:
            lowered = part.lower()
            if lowered not in seen:
                seen.add(lowered)
                unique_parts.append(part)
        keywords = " ".join(unique_parts)

        seniority = next((t for t in _SENIORITY_TERMS if t in goal_l), None)
        remote = True if "remote" in goal_l or candidate.open_to_remote else None
        location = candidate.preferred_locations[0] if candidate.preferred_locations else None

        plan = Plan(
            objective=f"Apply to a strong {target_role} match for {candidate.full_name}.",
            target_role=target_role,
            steps=[PlanStep(name=n, description=d) for n, d in STANDARD_STEPS],
            notes=["Heuristic plan (no LLM configured)."],
        )
        query = JobSearchQuery(
            keywords=keywords or target_role,
            location=location,
            remote=remote,
            seniority=seniority,
            limit=self.settings.max_jobs,
        )
        return plan, query
