"""Tests for the domain schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from jobpilot.schemas.application import (
    ApplicationForm,
    FieldType,
    FormField,
)
from jobpilot.schemas.candidate import CandidateProfile
from jobpilot.schemas.documents import CoverLetter
from jobpilot.schemas.job import Job
from jobpilot.schemas.state import AgentLog, log


def test_candidate_email_validation():
    with pytest.raises(ValidationError):
        CandidateProfile(full_name="X", email="not-an-email")
    ok = CandidateProfile(full_name="X", email="x@y.co")
    assert ok.email == "x@y.co"


def test_job_application_url_prefers_apply_url():
    job = Job(id="1", title="t", company="c", url="https://a", apply_url="https://b/apply")
    assert job.application_url == "https://b/apply"
    job2 = Job(id="2", title="t", company="c", url="https://a")
    assert job2.application_url == "https://a"


def test_cover_letter_text_and_word_count():
    cl = CoverLetter(job_id="1", body="Hello there friend", signature="Ada")
    assert cl.word_count == 3
    assert cl.greeting in cl.text
    assert "Ada" in cl.text


def test_application_form_field_helpers():
    form = ApplicationForm(
        url="https://x",
        fields=[
            FormField(selector="#a", field_type=FieldType.TEXT, required=True, filled=True),
            FormField(selector="#b", field_type=FieldType.FILE, required=True, filled=False),
            FormField(selector="#c", field_type=FieldType.TEXT, required=False, filled=False),
        ],
    )
    assert len(form.filled_fields) == 1
    assert len(form.unfilled_required) == 1
    assert form.unfilled_required[0].selector == "#b"


def test_log_helper():
    entries = log("planner", "did a thing")
    assert len(entries) == 1
    assert isinstance(entries[0], AgentLog)
    assert entries[0].agent == "planner"
    assert entries[0].timestamp  # auto-stamped
