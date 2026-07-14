"""Application-form automation.

This module exposes a small :class:`FormFiller` interface with two
implementations:

* :class:`PlaywrightFormFiller` drives a real Chromium browser to detect and
  fill live application forms.
* :class:`SimulatedFormFiller` fabricates a standard application form and fills
  it entirely offline, so the pipeline is runnable and testable without a
  browser, network, or real job site.

**Safety:** ``preview`` never submits. ``submit`` is the only method that clicks
a submit control, and the orchestrator only ever calls it after explicit human
approval (and only when ``browser_allow_submit`` is enabled).
"""

from __future__ import annotations

import contextlib
import html
import re
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field

from jobpilot.config import Settings, get_settings
from jobpilot.logging_config import get_logger
from jobpilot.schemas.application import (
    ApplicationForm,
    ApplicationResult,
    ApplicationStatus,
    FieldType,
    FormField,
)
from jobpilot.schemas.candidate import CandidateProfile
from jobpilot.schemas.documents import CoverLetter, TailoredResume
from jobpilot.schemas.job import Job

logger = get_logger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

try:  # Playwright is a core dependency, but browsers may not be installed.
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - only when playwright is absent
    PLAYWRIGHT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Application context + heuristic field mapping (pure, unit-testable)
# ---------------------------------------------------------------------------


class ApplicationContext(BaseModel):
    """The data used to answer application-form fields."""

    full_name: str
    email: str
    phone: str | None = None
    location: str | None = None
    links: dict[str, str] = Field(default_factory=dict)
    resume_markdown: str | None = None
    resume_path: str | None = None
    cover_letter_text: str | None = None
    open_to_remote: bool = True
    answers: dict[str, str] = Field(default_factory=dict)

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0] if self.full_name.strip() else ""

    @property
    def last_name(self) -> str:
        parts = self.full_name.split()
        return parts[-1] if len(parts) > 1 else ""


def build_context(
    candidate: CandidateProfile,
    resume: TailoredResume | None = None,
    cover_letter: CoverLetter | None = None,
    resume_path: str | None = None,
) -> ApplicationContext:
    """Assemble an :class:`ApplicationContext` from the run's artefacts."""
    return ApplicationContext(
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        location=candidate.location,
        links=dict(candidate.links),
        resume_markdown=resume.markdown if resume else None,
        resume_path=resume_path,
        cover_letter_text=cover_letter.text if cover_letter else None,
        open_to_remote=candidate.open_to_remote,
    )


def _haystack(field: FormField) -> str:
    return " ".join(filter(None, [field.label, field.name])).lower()


def resolve_value(field: FormField, ctx: ApplicationContext) -> str | None:
    """Heuristically choose a value for ``field`` from the context.

    Returns ``None`` when no confident answer exists, so the field is left for a
    human to complete.
    """
    text = _haystack(field)

    def has(*needles: str) -> bool:
        return any(n in text for n in needles)

    if field.field_type == FieldType.FILE or has("resume", "cv", "upload"):
        return ctx.resume_path
    if field.field_type == FieldType.EMAIL or has("email", "e-mail"):
        return ctx.email
    if field.field_type == FieldType.PHONE or has("phone", "mobile", "telephone", "tel"):
        return ctx.phone
    if has("linkedin"):
        return ctx.links.get("linkedin")
    if has("github"):
        return ctx.links.get("github")
    if has("portfolio", "website", "personal site"):
        return ctx.links.get("portfolio") or ctx.links.get("website")
    if has("first name", "given name", "forename"):
        return ctx.first_name
    if has("last name", "surname", "family name"):
        return ctx.last_name
    if has("full name") or text.strip() in {"name", "your name", "applicant name"}:
        return ctx.full_name
    if has("location", "city", "where are you", "current location"):
        return ctx.location
    if has("cover letter", "why do you", "tell us", "motivation", "message"):
        return ctx.cover_letter_text
    if field.field_type == FieldType.CHECKBOX and has("remote", "relocate"):
        return "true" if ctx.open_to_remote else "false"
    if has("work authorization", "authorized to work", "eligible to work"):
        return _pick_option(field, prefer=["yes", "authorized"])
    if has("name"):  # generic single "name" field
        return ctx.full_name
    return ctx.answers.get(field.name or "") or ctx.answers.get(field.label or "")


def _pick_option(field: FormField, prefer: list[str]) -> str | None:
    if not field.options:
        return None
    for want in prefer:
        for opt in field.options:
            if want in opt.lower():
                return opt
    return field.options[0]


def map_fields(fields: list[FormField], ctx: ApplicationContext) -> list[FormField]:
    """Return copies of ``fields`` with proposed values and notes attached."""
    mapped: list[FormField] = []
    for field in fields:
        value = resolve_value(field, ctx)
        note = field.note
        if value is None and field.required:
            note = "Requires human input — no confident automated answer."
        mapped.append(field.model_copy(update={"value": value, "note": note}))
    return mapped


def _field_type(raw: str) -> FieldType:
    raw = raw.lower()
    mapping = {
        "email": FieldType.EMAIL,
        "tel": FieldType.PHONE,
        "phone": FieldType.PHONE,
        "url": FieldType.URL,
        "textarea": FieldType.TEXTAREA,
        "select": FieldType.SELECT,
        "select-one": FieldType.SELECT,
        "checkbox": FieldType.CHECKBOX,
        "radio": FieldType.RADIO,
        "file": FieldType.FILE,
        "text": FieldType.TEXT,
    }
    return mapping.get(raw, FieldType.UNKNOWN)


def artifact_dir(settings: Settings, job: Job) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", job.id) or "job"
    path = settings.artifacts_dir / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# FormFiller interface
# ---------------------------------------------------------------------------


class FormFiller(ABC):
    """Interface for previewing and submitting an application form."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    async def preview(self, job: Job, ctx: ApplicationContext) -> ApplicationForm:
        """Open the form, propose answers, capture a preview — never submit."""

    @abstractmethod
    async def submit(
        self, job: Job, form: ApplicationForm, overrides: dict[str, str]
    ) -> ApplicationResult:
        """Fill the form (with human overrides applied) and submit it."""


# ---------------------------------------------------------------------------
# Simulated filler (offline, no browser)
# ---------------------------------------------------------------------------

_STANDARD_FORM: list[dict] = [
    {
        "selector": 'input[name="full_name"]',
        "label": "Full name",
        "name": "full_name",
        "field_type": FieldType.TEXT,
        "required": True,
    },
    {
        "selector": 'input[name="email"]',
        "label": "Email",
        "name": "email",
        "field_type": FieldType.EMAIL,
        "required": True,
    },
    {
        "selector": 'input[name="phone"]',
        "label": "Phone",
        "name": "phone",
        "field_type": FieldType.PHONE,
        "required": False,
    },
    {
        "selector": 'input[name="location"]',
        "label": "Location",
        "name": "location",
        "field_type": FieldType.TEXT,
        "required": False,
    },
    {
        "selector": 'input[name="linkedin"]',
        "label": "LinkedIn URL",
        "name": "linkedin",
        "field_type": FieldType.URL,
        "required": False,
    },
    {
        "selector": 'input[name="github"]',
        "label": "GitHub URL",
        "name": "github",
        "field_type": FieldType.URL,
        "required": False,
    },
    {
        "selector": 'input[name="resume"]',
        "label": "Resume / CV",
        "name": "resume",
        "field_type": FieldType.FILE,
        "required": True,
    },
    {
        "selector": 'textarea[name="cover_letter"]',
        "label": "Cover letter",
        "name": "cover_letter",
        "field_type": FieldType.TEXTAREA,
        "required": False,
    },
    {
        "selector": 'select[name="work_authorization"]',
        "label": "Authorized to work?",
        "name": "work_authorization",
        "field_type": FieldType.SELECT,
        "required": True,
        "options": ["Yes", "No"],
    },
]


class SimulatedFormFiller(FormFiller):
    """Fabricates and fills a standard application form without a browser."""

    async def preview(self, job: Job, ctx: ApplicationContext) -> ApplicationForm:
        fields = [FormField(**spec) for spec in _STANDARD_FORM]
        fields = map_fields(fields, ctx)
        for field in fields:
            field.filled = field.value is not None

        preview_path = artifact_dir(self.settings, job) / "application_preview.html"
        preview_path.write_text(_render_form_html(job, fields), encoding="utf-8")

        logger.info(
            "browser.simulated.preview",
            job_id=job.id,
            fields=len(fields),
            filled=sum(f.filled for f in fields),
        )
        return ApplicationForm(
            url=job.application_url,
            detected=True,
            fields=fields,
            html_snapshot_path=str(preview_path),
            notes=["Simulated form (no live browser). Values proposed from candidate profile."],
        )

    async def submit(
        self, job: Job, form: ApplicationForm, overrides: dict[str, str]
    ) -> ApplicationResult:
        for field in form.fields:
            if field.selector in overrides:
                field.value = overrides[field.selector]
                field.filled = True

        confirmation_path = artifact_dir(self.settings, job) / "application_submitted.html"
        confirmation_path.write_text(
            _render_form_html(job, form.fields, submitted=True), encoding="utf-8"
        )
        logger.info("browser.simulated.submit", job_id=job.id)
        return ApplicationResult(
            job_id=job.id,
            status=ApplicationStatus.SUBMITTED,
            form=form,
            submitted=True,
            confirmation="Simulated submission recorded (no live browser).",
            screenshot_path=str(confirmation_path),
        )


def _render_form_html(job: Job, fields: list[FormField], submitted: bool = False) -> str:
    banner = "SUBMITTED" if submitted else "PREVIEW — not submitted"
    rows = "\n".join(
        "<tr><td>{label}</td><td><code>{selector}</code></td><td>{value}</td>"
        "<td>{status}</td></tr>".format(
            label=html.escape(f.label or f.name or ""),
            selector=html.escape(f.selector),
            value=html.escape((f.value or "")[:500]),
            status="filled" if f.filled else ("REQUIRED" if f.required else "empty"),
        )
        for f in fields
    )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(job.title)} — {banner}</title></head><body>"
        f"<h1>{html.escape(job.title)} @ {html.escape(job.company)}</h1>"
        f"<p><strong>{banner}</strong> — <a href='{html.escape(job.application_url)}'>"
        f"{html.escape(job.application_url)}</a></p>"
        f"<table border='1' cellpadding='6' cellspacing='0'>"
        f"<tr><th>Field</th><th>Selector</th><th>Value</th><th>Status</th></tr>"
        f"{rows}</table></body></html>"
    )


# ---------------------------------------------------------------------------
# Playwright filler (live browser)
# ---------------------------------------------------------------------------

# JS that tags every visible form control and returns its metadata.
_DETECT_JS = """
() => {
  const nodes = Array.from(document.querySelectorAll('input, textarea, select'));
  const skip = new Set(['hidden', 'submit', 'button', 'reset', 'image']);
  const out = [];
  let idx = 0;
  for (const el of nodes) {
    const type = (el.getAttribute('type') || el.tagName).toLowerCase();
    if (skip.has(type)) continue;
    el.setAttribute('data-jobpilot-idx', String(idx));
    let label = '';
    if (el.id) {
      const lab = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (lab) label = lab.innerText;
    }
    if (!label && el.closest('label')) label = el.closest('label').innerText;
    if (!label) label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
    const options = el.tagName.toLowerCase() === 'select'
      ? Array.from(el.options).map(o => o.textContent.trim()).filter(Boolean) : [];
    out.push({
      selector: '[data-jobpilot-idx="' + idx + '"]',
      name: el.getAttribute('name') || '',
      label: (label || '').trim().slice(0, 200),
      type: type,
      required: el.hasAttribute('required') || el.getAttribute('aria-required') === 'true',
      options: options,
    });
    idx++;
  }
  return out;
}
"""

_SUBMIT_SELECTORS = (
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Submit")',
    'button:has-text("Apply")',
    'button:has-text("Send application")',
)


class PlaywrightFormFiller(FormFiller):
    """Drives a real Chromium browser to detect, fill and submit forms."""

    async def _open_page(self, browser):
        """A page with a realistic UA/viewport (some ATS block default headless)."""
        return await browser.new_page(
            user_agent=_USER_AGENT, viewport={"width": 1280, "height": 1600}
        )

    async def _navigate(self, page, url: str) -> None:
        await page.goto(
            url, timeout=self.settings.browser_timeout_ms, wait_until="domcontentloaded"
        )
        # Give JS-rendered forms a moment to attach their fields.
        with contextlib.suppress(Exception):
            await page.wait_for_selector("input, textarea", timeout=8000)

    async def _detect(self, page) -> list[FormField]:
        raw = await page.evaluate(_DETECT_JS)
        fields: list[FormField] = []
        for item in raw:
            fields.append(
                FormField(
                    selector=item["selector"],
                    name=item.get("name") or None,
                    label=item.get("label") or None,
                    field_type=_field_type(item.get("type", "")),
                    required=bool(item.get("required")),
                    options=item.get("options") or [],
                )
            )
        return fields

    async def _fill(self, page, fields: list[FormField], overrides: dict[str, str]) -> None:
        for field in fields:
            value = overrides.get(field.selector, field.value)
            if not value:
                continue
            try:
                if field.field_type == FieldType.SELECT:
                    try:
                        await page.select_option(field.selector, value=value)
                    except Exception:
                        await page.select_option(field.selector, label=value)
                elif field.field_type == FieldType.CHECKBOX:
                    if str(value).lower() in {"true", "yes", "1", "on"}:
                        await page.check(field.selector)
                elif field.field_type == FieldType.FILE:
                    if value and Path(value).exists():
                        await page.set_input_files(field.selector, value)
                    else:
                        field.note = "Resume file not found; upload skipped."
                        continue
                else:
                    await page.fill(field.selector, value)
                field.filled = True
            except Exception as exc:  # keep going; record the failure per-field
                field.note = f"fill failed: {exc}"
                logger.warning("browser.fill_failed", selector=field.selector, error=str(exc))

    async def preview(self, job: Job, ctx: ApplicationContext) -> ApplicationForm:
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not available in this environment.")

        art_dir = artifact_dir(self.settings, job)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.settings.browser_headless)
            page = await self._open_page(browser)
            try:
                await self._navigate(page, job.application_url)
                fields = await self._detect(page)
                fields = map_fields(fields, ctx)
                await self._fill(page, fields, overrides={})
                shot = str(art_dir / "application_preview.png")
                await page.screenshot(path=shot, full_page=True)
                html_path = art_dir / "application_preview.html"
                html_path.write_text(await page.content(), encoding="utf-8")
            finally:
                await browser.close()

        logger.info("browser.playwright.preview", job_id=job.id, fields=len(fields))
        return ApplicationForm(
            url=job.application_url,
            detected=bool(fields),
            fields=fields,
            screenshot_path=shot,
            html_snapshot_path=str(html_path),
            notes=["Live Playwright preview. Review the screenshot before approving."],
        )

    async def submit(
        self, job: Job, form: ApplicationForm, overrides: dict[str, str]
    ) -> ApplicationResult:
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not available in this environment.")

        art_dir = artifact_dir(self.settings, job)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.settings.browser_headless)
            page = await self._open_page(browser)
            try:
                await self._navigate(page, job.application_url)
                # Re-detect to obtain fresh element handles, then carry over values.
                live = await self._detect(page)
                by_selector = {f.selector: f for f in form.fields}
                for field in live:
                    prior = by_selector.get(field.selector)
                    if prior:
                        field.value = prior.value
                await self._fill(page, live, overrides)

                clicked = await self._click_submit(page)
                await page.wait_for_timeout(1500)
                shot = str(art_dir / "application_submitted.png")
                await page.screenshot(path=shot, full_page=True)
                confirmation = (await page.inner_text("body"))[:500] if clicked else None
            finally:
                await browser.close()

        status = ApplicationStatus.SUBMITTED if clicked else ApplicationStatus.FAILED
        logger.info("browser.playwright.submit", job_id=job.id, submitted=clicked)
        return ApplicationResult(
            job_id=job.id,
            status=status,
            form=form,
            submitted=clicked,
            confirmation=confirmation,
            screenshot_path=shot,
            error=None if clicked else "Could not locate a submit control.",
        )

    async def _click_submit(self, page) -> bool:
        for selector in _SUBMIT_SELECTORS:
            try:
                locator = page.locator(selector).first
                if await locator.count() and await locator.is_visible():
                    await locator.click(timeout=self.settings.browser_timeout_ms)
                    return True
            except Exception:  # pragma: no cover - site-specific
                continue
        return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_form_filler(job: Job, settings: Settings | None = None) -> FormFiller:
    """Choose a filler for ``job`` based on settings and the job's URL."""
    settings = settings or get_settings()
    mode = settings.browser_mode

    if mode == "simulated":
        return SimulatedFormFiller(settings)
    if mode == "playwright":
        return PlaywrightFormFiller(settings)

    # auto: use a live browser only for real http(s) forms when available.
    url = job.application_url
    is_live = url.startswith("http") and job.source != "sample"
    if is_live and PLAYWRIGHT_AVAILABLE:
        return PlaywrightFormFiller(settings)
    return SimulatedFormFiller(settings)
