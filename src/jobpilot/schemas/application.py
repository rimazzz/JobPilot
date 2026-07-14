"""Application, form, review and approval models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FieldType(StrEnum):
    TEXT = "text"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    FILE = "file"
    UNKNOWN = "unknown"


class FormField(BaseModel):
    """A single detected form field and the value JobPilot proposes for it."""

    model_config = ConfigDict(extra="forbid")

    selector: str
    label: str | None = None
    name: str | None = None
    field_type: FieldType = FieldType.UNKNOWN
    value: str | None = None
    required: bool = False
    options: list[str] = Field(default_factory=list)
    filled: bool = False
    note: str | None = None


class ApplicationForm(BaseModel):
    """A snapshot of an application form and its proposed answers."""

    model_config = ConfigDict(extra="forbid")

    url: str
    detected: bool = False
    fields: list[FormField] = Field(default_factory=list)
    screenshot_path: str | None = None
    html_snapshot_path: str | None = None
    notes: list[str] = Field(default_factory=list)

    @property
    def filled_fields(self) -> list[FormField]:
        return [f for f in self.fields if f.filled]

    @property
    def unfilled_required(self) -> list[FormField]:
        return [f for f in self.fields if f.required and not f.filled]


class ApplicationStatus(StrEnum):
    DRAFTED = "drafted"
    FILLED = "filled"
    AWAITING_APPROVAL = "awaiting_approval"
    SUBMITTED = "submitted"
    SKIPPED = "skipped"
    FAILED = "failed"


class ApplicationResult(BaseModel):
    """The outcome of interacting with a job's application form."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: ApplicationStatus = ApplicationStatus.DRAFTED
    form: ApplicationForm | None = None
    submitted: bool = False
    confirmation: str | None = None
    screenshot_path: str | None = None
    error: str | None = None


class ReviewVerdict(StrEnum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


class ReviewItem(BaseModel):
    """A single checklist item in the Reviewer's report."""

    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    comment: str = ""


class Review(BaseModel):
    """The Reviewer agent's quality assessment prior to human approval."""

    model_config = ConfigDict(extra="forbid")

    verdict: ReviewVerdict = ReviewVerdict.REVISE
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    summary: str = ""
    checklist: list[ReviewItem] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    """A human's decision on whether to submit the application."""

    model_config = ConfigDict(extra="forbid")

    approved: bool
    notes: str | None = None
    #: Optional per-field value overrides keyed by form field selector.
    field_overrides: dict[str, str] = Field(default_factory=dict)
