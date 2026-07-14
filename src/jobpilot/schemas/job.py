"""Job search query and job posting models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class JobSearchQuery(BaseModel):
    """A normalised job-search request.

    The Planner agent derives this from the candidate profile and the free-text
    goal; the Search agent executes it against a job-search provider.
    """

    model_config = ConfigDict(extra="forbid")

    keywords: str
    location: str | None = None
    remote: bool | None = None
    seniority: str | None = None
    limit: int = Field(default=5, ge=1, le=50)
    sources: list[str] = Field(default_factory=list)


class Job(BaseModel):
    """A job posting returned by a search provider."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    company: str
    location: str | None = None
    remote: bool = False
    url: str
    apply_url: str | None = None
    description: str = ""
    salary: str | None = None
    posted_at: str | None = None
    source: str = "unknown"
    tags: list[str] = Field(default_factory=list)

    @property
    def application_url(self) -> str:
        """The best URL to start an application from."""
        return self.apply_url or self.url
