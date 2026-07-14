"""Candidate profile models — the applicant's structured resume/context."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Experience(BaseModel):
    """A single role in the candidate's work history."""

    model_config = ConfigDict(extra="forbid")

    company: str
    title: str
    start_date: str | None = None
    end_date: str | None = None  # ``None`` implies "Present".
    location: str | None = None
    highlights: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class Education(BaseModel):
    """An education entry."""

    model_config = ConfigDict(extra="forbid")

    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    graduation_year: str | None = None
    details: str | None = None


class CandidateProfile(BaseModel):
    """Everything JobPilot knows about the applicant.

    This is the primary input to a run. It doubles as the candidate's base
    resume: the Resume agent tailors *from* this structured data.
    """

    model_config = ConfigDict(extra="forbid")

    full_name: str
    email: str
    phone: str | None = None
    location: str | None = None
    headline: str | None = Field(
        default=None, description="Short professional tagline, e.g. 'Senior Python Engineer'."
    )
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    links: dict[str, str] = Field(
        default_factory=dict, description="Named links, e.g. {'github': 'https://...'}."
    )
    desired_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    open_to_remote: bool = True
    years_experience: float | None = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value):
            raise ValueError(f"invalid email address: {value!r}")
        return value

    def skills_text(self) -> str:
        """Comma-separated skills, convenient for prompts."""
        return ", ".join(self.skills)
