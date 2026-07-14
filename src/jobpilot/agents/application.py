"""Application agent — fills (and, only after approval, submits) the form.

Exposes two graph nodes:

* :meth:`fill` opens the application form and proposes answers. It never
  submits. The result is what the Reviewer and the human see.
* :meth:`submit` is reached only on the approved branch of the graph and only
  submits when ``browser_allow_submit`` is enabled.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.language_models import BaseChatModel

from jobpilot.agents.base import BaseAgent
from jobpilot.config import Settings
from jobpilot.schemas.application import ApplicationResult, ApplicationStatus
from jobpilot.schemas.documents import CoverLetter, TailoredResume
from jobpilot.schemas.job import Job
from jobpilot.schemas.state import AgentState, RunStatus, log
from jobpilot.tools.browser import FormFiller, artifact_dir, build_context, build_form_filler

FillerFactory = Callable[[Job, Settings], FormFiller]


class ApplicationAgent(BaseAgent):
    name = "application"

    def __init__(
        self,
        settings: Settings,
        filler_factory: FillerFactory | None = None,
        llm: BaseChatModel | None = None,
    ) -> None:
        super().__init__(settings, llm)
        self.filler_factory = filler_factory or build_form_filler

    # -- Node: fill (preview only) ------------------------------------------
    async def fill(self, state: AgentState) -> dict:
        job = state.get("selected_job")
        if job is None:
            return {"status": RunStatus.NO_JOBS}
        candidate = state["candidate"]
        resume = state.get("resume")
        cover = state.get("cover_letter")

        resume_path = self._write_documents(job, resume, cover)
        ctx = build_context(candidate, resume, cover, resume_path=resume_path)
        filler = self.filler_factory(job, self.settings)

        try:
            form = await filler.preview(job, ctx)
        except Exception as exc:
            self.logger.error("application.fill_failed", job_id=job.id, error=str(exc))
            result = ApplicationResult(
                job_id=job.id, status=ApplicationStatus.FAILED, error=str(exc)
            )
            return {
                "application": result,
                "status": RunStatus.FILLING,
                "errors": [f"Form fill failed: {exc}"],
                "logs": log(self.name, f"Form fill failed: {exc}", level="error"),
            }

        result = ApplicationResult(
            job_id=job.id,
            status=ApplicationStatus.FILLED,
            form=form,
            screenshot_path=form.screenshot_path,
        )
        return {
            "application": result,
            "status": RunStatus.FILLING,
            "logs": log(
                self.name,
                f"Filled {len(form.filled_fields)}/{len(form.fields)} fields "
                f"({form.url}). Awaiting review.",
            ),
        }

    # -- Node: submit (post-approval) ---------------------------------------
    async def submit(self, state: AgentState) -> dict:
        job = state.get("selected_job")
        application = state.get("application")
        approval = state.get("approval")

        if job is None or application is None or application.form is None:
            return {"status": RunStatus.FAILED, "errors": ["Nothing to submit."]}

        if approval is None or not approval.approved:
            application.status = ApplicationStatus.SKIPPED
            return {
                "application": application,
                "status": RunStatus.REJECTED,
                "logs": log(self.name, "Submission skipped — not approved.", level="warning"),
            }

        if not self.settings.browser_allow_submit:
            application.status = ApplicationStatus.SKIPPED
            return {
                "application": application,
                "status": RunStatus.COMPLETED,
                "logs": log(
                    self.name,
                    "Approved, but submission is disabled (browser_allow_submit=false).",
                    level="warning",
                ),
            }

        filler = self.filler_factory(job, self.settings)
        try:
            result = await filler.submit(job, application.form, approval.field_overrides)
        except Exception as exc:
            self.logger.error("application.submit_failed", job_id=job.id, error=str(exc))
            application.status = ApplicationStatus.FAILED
            application.error = str(exc)
            return {
                "application": application,
                "status": RunStatus.FAILED,
                "errors": [f"Submission failed: {exc}"],
                "logs": log(self.name, f"Submission failed: {exc}", level="error"),
            }

        return {
            "application": result,
            "status": RunStatus.SUBMITTING,
            "logs": log(self.name, f"Submitted application to {job.company}."),
        }

    # -- helpers ------------------------------------------------------------
    def _write_documents(
        self, job: Job, resume: TailoredResume | None, cover: CoverLetter | None
    ) -> str | None:
        """Persist resume/cover-letter artefacts; return the resume file path."""
        directory = artifact_dir(self.settings, job)
        resume_path: str | None = None
        if resume is not None:
            path = directory / "resume.md"
            path.write_text(resume.markdown, encoding="utf-8")
            resume_path = str(path)
        if cover is not None:
            (directory / "cover_letter.txt").write_text(cover.text, encoding="utf-8")
        return resume_path
