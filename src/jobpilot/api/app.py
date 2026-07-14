"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from jobpilot import __version__
from jobpilot.api.routes import router
from jobpilot.config import Settings, get_settings
from jobpilot.logging_config import configure_logging, get_logger
from jobpilot.orchestrator import Orchestrator

logger = get_logger("api")

DESCRIPTION = """
JobPilot is a modular multi-agent job-application assistant.

Start a run with `POST /applications`; the agents plan, search, analyse, and
draft a tailored resume, cover letter and filled application form, then **pause
for your approval**. Inspect the drafts with `GET /applications/{thread_id}` and
approve or reject with `POST /applications/{thread_id}/approve`. Nothing is ever
submitted without explicit approval.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.orchestrator = Orchestrator(settings)
        logger.info(
            "api.startup",
            provider=settings.llm_provider,
            llm_enabled=bool(settings.active_api_key),
            search_provider=settings.search_provider,
            browser_mode=settings.browser_mode,
        )
        yield
        logger.info("api.shutdown")

    app = FastAPI(
        title="JobPilot",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.get("/", tags=["meta"])
    async def root() -> dict:
        return {
            "name": "JobPilot",
            "version": __version__,
            "docs": "/docs",
            "health": "/health",
        }

    return app
