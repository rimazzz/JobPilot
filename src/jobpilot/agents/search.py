"""Search agent — runs the job search and selects a target posting."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from jobpilot.agents.base import BaseAgent
from jobpilot.config import Settings
from jobpilot.schemas.state import AgentState, RunStatus, log
from jobpilot.tools.job_search import JobSearchProvider, build_search_provider


class SearchAgent(BaseAgent):
    name = "search"

    def __init__(
        self,
        settings: Settings,
        provider: JobSearchProvider | None = None,
        llm: BaseChatModel | None = None,
    ) -> None:
        super().__init__(settings, llm)
        self.provider = provider or build_search_provider(settings)

    async def run(self, state: AgentState) -> dict:
        query = state["query"]
        try:
            jobs = await self.provider.search(query)
        except Exception as exc:
            self.logger.error("search.failed", error=str(exc))
            return {
                "jobs": [],
                "selected_job": None,
                "status": RunStatus.NO_JOBS,
                "errors": [f"Job search failed: {exc}"],
                "logs": log(self.name, f"Search failed: {exc}", level="error"),
            }

        selected = jobs[0] if jobs else None
        if selected is None:
            return {
                "jobs": [],
                "selected_job": None,
                "status": RunStatus.NO_JOBS,
                "logs": log(self.name, "No jobs matched the query.", level="warning"),
            }

        return {
            "jobs": jobs,
            "selected_job": selected,
            "status": RunStatus.SEARCHING,
            "logs": log(
                self.name,
                f"Found {len(jobs)} job(s); selected '{selected.title}' @ {selected.company}.",
            ),
        }
