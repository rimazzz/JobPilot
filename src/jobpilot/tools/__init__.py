"""External-capability tools: job search and browser form automation."""

from __future__ import annotations

from jobpilot.tools.browser import (
    ApplicationContext,
    FormFiller,
    PlaywrightFormFiller,
    SimulatedFormFiller,
    artifact_dir,
    build_context,
    build_form_filler,
    map_fields,
    resolve_value,
)
from jobpilot.tools.job_search import (
    GreenhouseJobSearchProvider,
    JobSearchProvider,
    RemoteJobSearchProvider,
    RemoteOKJobSearchProvider,
    RemotiveJobSearchProvider,
    SampleJobSearchProvider,
    build_search_provider,
)

__all__ = [
    "JobSearchProvider",
    "SampleJobSearchProvider",
    "GreenhouseJobSearchProvider",
    "RemoteOKJobSearchProvider",
    "RemotiveJobSearchProvider",
    "RemoteJobSearchProvider",
    "build_search_provider",
    "FormFiller",
    "SimulatedFormFiller",
    "PlaywrightFormFiller",
    "ApplicationContext",
    "artifact_dir",
    "build_context",
    "build_form_filler",
    "map_fields",
    "resolve_value",
]
