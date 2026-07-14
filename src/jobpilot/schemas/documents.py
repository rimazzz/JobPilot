"""Generated document models: job analysis, tailored resume, cover letter."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Recommendation(StrEnum):
    """How strongly the analysis recommends applying to a job."""

    APPLY = "apply"
    MAYBE = "maybe"
    SKIP = "skip"


class JobAnalysis(BaseModel):
    """The Job Analyzer's assessment of a posting against the candidate."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    match_score: float = Field(ge=0.0, le=100.0)
    recommendation: Recommendation = Recommendation.MAYBE
    summary: str = ""
    key_requirements: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    """A resume tailored to a specific job."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    headline: str
    summary: str
    highlighted_skills: list[str] = Field(default_factory=list)
    emphasized_experience: list[str] = Field(default_factory=list)
    markdown: str
    changes: list[str] = Field(
        default_factory=list, description="Human-readable notes on what was tailored."
    )


class CoverLetter(BaseModel):
    """A cover letter tailored to a specific job."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    greeting: str = "Dear Hiring Manager,"
    body: str
    closing: str = "Sincerely,"
    signature: str = ""

    @property
    def text(self) -> str:
        """The full rendered letter."""
        parts = [self.greeting, "", self.body.strip(), "", self.closing, self.signature]
        return "\n".join(p for p in parts if p is not None).strip()

    @property
    def word_count(self) -> int:
        return len(self.body.split())
