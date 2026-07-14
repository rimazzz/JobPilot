"""Tests for form mapping and the simulated browser filler."""

from __future__ import annotations

from jobpilot.schemas.application import FieldType, FormField
from jobpilot.tools.browser import (
    ApplicationContext,
    PlaywrightFormFiller,
    SimulatedFormFiller,
    build_context,
    build_form_filler,
    map_fields,
    resolve_value,
)


def _ctx() -> ApplicationContext:
    return ApplicationContext(
        full_name="Ada Lovelace",
        email="ada@example.com",
        phone="+1-555-0100",
        location="Remote",
        links={"linkedin": "https://linkedin.com/in/ada", "github": "https://github.com/ada"},
        resume_path="/tmp/resume.md",
        cover_letter_text="Dear team, I am excited...",
    )


def test_resolve_value_matches_by_label():
    ctx = _ctx()
    assert resolve_value(FormField(selector="#e", label="Email address"), ctx) == ctx.email
    assert resolve_value(FormField(selector="#p", label="Phone"), ctx) == ctx.phone
    assert resolve_value(FormField(selector="#l", label="LinkedIn"), ctx) == ctx.links["linkedin"]
    assert resolve_value(FormField(selector="#n", label="Full name"), ctx) == ctx.full_name
    file_field = FormField(selector="#r", label="Resume", field_type=FieldType.FILE)
    assert resolve_value(file_field, ctx) == ctx.resume_path


def test_resolve_first_last_name():
    ctx = _ctx()
    assert resolve_value(FormField(selector="#f", label="First name"), ctx) == "Ada"
    assert resolve_value(FormField(selector="#l", label="Last name"), ctx) == "Lovelace"


def test_map_fields_flags_required_without_answer():
    ctx = _ctx()
    fields = [FormField(selector="#x", label="Desired salary", required=True)]
    mapped = map_fields(fields, ctx)
    assert mapped[0].value is None
    assert "human input" in (mapped[0].note or "").lower()


async def test_simulated_filler_preview_and_submit(settings, job):
    ctx = _ctx()
    filler = SimulatedFormFiller(settings)

    form = await filler.preview(job, ctx)
    assert form.detected
    assert len(form.filled_fields) >= 5
    assert form.html_snapshot_path and form.html_snapshot_path.endswith(".html")

    result = await filler.submit(job, form, overrides={'input[name="phone"]': "+1-555-9999"})
    assert result.submitted is True
    assert result.status.value == "submitted"
    phone_field = next(f for f in result.form.fields if f.name == "phone")
    assert phone_field.value == "+1-555-9999"


def test_build_form_filler_selects_simulated_for_sample(settings, job):
    # sample-source job in auto mode -> simulated
    assert isinstance(build_form_filler(job, settings), SimulatedFormFiller)


def test_build_form_filler_playwright_when_forced(settings, job):
    forced = settings.model_copy(update={"browser_mode": "playwright"})
    assert isinstance(build_form_filler(job, forced), PlaywrightFormFiller)


def test_build_context_from_candidate(candidate):
    ctx = build_context(candidate)
    assert ctx.full_name == candidate.full_name
    assert ctx.links.get("github")
