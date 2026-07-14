"""Shared pytest fixtures and test doubles."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from jobpilot.config import Settings
from jobpilot.orchestrator import Orchestrator
from jobpilot.schemas.candidate import CandidateProfile, Education, Experience
from jobpilot.schemas.documents import JobAnalysis, Recommendation
from jobpilot.schemas.job import Job

# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------


class _FakeStructuredRunnable:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, _messages):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeChatModel:
    """A minimal stand-in for a LangChain chat model.

    ``structured`` is returned from ``with_structured_output(...).ainvoke``;
    ``text`` is returned as ``.content`` from ``ainvoke``. Set ``error`` to make
    every call raise, which exercises the agents' heuristic fallback.
    """

    def __init__(self, *, structured=None, text: str = "A concise summary.", error=None):
        self._structured = structured
        self._text = text
        self._error = error

    def with_structured_output(self, _schema):
        return _FakeStructuredRunnable(self._error or self._structured)

    async def ainvoke(self, _messages):
        if self._error is not None:
            raise self._error
        return SimpleNamespace(content=self._text)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Keep the cached process settings from leaking across tests."""
    from jobpilot.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Offline settings: no API key, simulated browser, sample search."""
    return Settings(
        anthropic_api_key="",
        openai_api_key="",
        llm_provider="anthropic",
        search_provider="sample",
        browser_mode="simulated",
        artifacts_dir=tmp_path / "artifacts",
        checkpoint_db=str(tmp_path / "ckpt.sqlite"),
        log_format="console",
    )


@pytest.fixture
def candidate() -> CandidateProfile:
    return CandidateProfile(
        full_name="Ada Lovelace",
        email="ada@example.com",
        phone="+1-555-0100",
        location="Remote",
        headline="Senior Python Engineer",
        summary="Backend engineer with 6 years building APIs.",
        skills=["Python", "FastAPI", "PostgreSQL", "AWS", "Docker", "asyncio"],
        experiences=[
            Experience(
                company="Acme",
                title="Senior Backend Engineer",
                start_date="2021",
                highlights=[
                    "Built FastAPI services on AWS handling 1M requests/day.",
                    "Scaled PostgreSQL to 10M rows with zero downtime.",
                ],
                technologies=["Python", "FastAPI", "AWS"],
            )
        ],
        education=[
            Education(
                institution="MIT",
                degree="BSc",
                field_of_study="Computer Science",
                graduation_year="2018",
            )
        ],
        desired_roles=["Senior Python Engineer"],
        preferred_locations=["Remote"],
        links={
            "github": "https://github.com/ada",
            "linkedin": "https://linkedin.com/in/ada",
        },
    )


@pytest.fixture
def job() -> Job:
    return Job(
        id="job-1",
        title="Senior Python Engineer",
        company="Northwind Labs",
        location="Remote",
        remote=True,
        url="https://example.com/jobs/1",
        apply_url="https://example.com/jobs/1/apply",
        description=(
            "Requirements: 5+ years of Python, strong FastAPI, PostgreSQL, AWS, Docker. "
            "Experience with CI/CD required. Kubernetes is a plus."
        ),
        source="sample",
        tags=["python", "fastapi", "postgresql", "aws", "docker", "kubernetes"],
    )


@pytest.fixture
def analysis(job) -> JobAnalysis:
    return JobAnalysis(
        job_id=job.id,
        match_score=85.0,
        recommendation=Recommendation.APPLY,
        summary="Strong match on core backend skills.",
        key_requirements=["5+ years Python", "FastAPI", "AWS"],
        matched_skills=["Python", "FastAPI", "PostgreSQL", "AWS"],
        missing_skills=["Kubernetes"],
        keywords=["python", "fastapi", "aws"],
        strengths=["Experience with Python", "Experience with FastAPI"],
        gaps=["Limited signal on Kubernetes"],
    )


@pytest.fixture
def orchestrator(settings) -> Orchestrator:
    return Orchestrator(settings=settings)
