"""FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from jobpilot.config import Settings
from jobpilot.orchestrator import Orchestrator


def get_orchestrator(request: Request) -> Orchestrator:
    """Return the process-wide orchestrator created during app start-up."""
    return request.app.state.orchestrator


def get_settings_dep(request: Request) -> Settings:
    """Return the settings bound to the running app."""
    return request.app.state.settings
