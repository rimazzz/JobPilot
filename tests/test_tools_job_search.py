"""Tests for the job-search providers."""

from __future__ import annotations

import pytest

from jobpilot.config import Settings
from jobpilot.schemas.job import Job, JobSearchQuery
from jobpilot.tools.job_search import (
    GreenhouseJobSearchProvider,
    RemoteJobSearchProvider,
    RemoteOKJobSearchProvider,
    RemotiveJobSearchProvider,
    SampleJobSearchProvider,
    _rank,
    build_search_provider,
    strip_html,
)


async def test_sample_search_ranks_by_relevance():
    provider = SampleJobSearchProvider()
    jobs = await provider.search(JobSearchQuery(keywords="python fastapi aws", limit=3))
    assert 1 <= len(jobs) <= 3
    # The senior python posting should rank first for these terms.
    assert "python" in jobs[0].title.lower() or "python" in jobs[0].tags


async def test_sample_search_respects_limit_and_remote():
    provider = SampleJobSearchProvider()
    jobs = await provider.search(JobSearchQuery(keywords="engineer", remote=True, limit=2))
    assert len(jobs) <= 2
    assert all(j.remote for j in jobs)


async def test_build_search_provider_default_is_sample():
    provider = build_search_provider(Settings(_env_file=None))
    assert isinstance(provider, SampleJobSearchProvider)


def test_remote_requires_url():
    with pytest.raises(ValueError):
        RemoteJobSearchProvider(api_url="")
    with pytest.raises(ValueError):
        build_search_provider(Settings(_env_file=None, search_provider="remote"))


def test_strip_html():
    assert strip_html("<p>Hello&nbsp;<b>world</b></p>") == "Hello  world"
    # Greenhouse double-encodes its content field.
    assert strip_html("&lt;p&gt;Build APIs&lt;/p&gt;") == "Build APIs"


def test_build_search_provider_greenhouse():
    provider = build_search_provider(
        Settings(_env_file=None, search_provider="greenhouse", greenhouse_companies="figma,stripe")
    )
    assert isinstance(provider, GreenhouseJobSearchProvider)
    assert provider.companies == ["figma", "stripe"]


def test_greenhouse_to_job_mapping():
    item = {
        "id": 5364702004,
        "title": "Senior Backend Engineer",
        "location": {"name": "Remote - US"},
        "absolute_url": "https://boards.greenhouse.io/figma/jobs/5364702004",
        "content": "&lt;p&gt;Build with Python&lt;/p&gt;",
        "updated_at": "2026-07-01T00:00:00Z",
        "departments": [{"name": "Engineering"}],
    }
    job = GreenhouseJobSearchProvider._to_job(item, "figma")
    assert job.id == "5364702004"
    assert job.company == "Figma"
    assert job.remote is True
    assert job.source == "greenhouse"
    assert job.url == "https://boards.greenhouse.io/figma/jobs/5364702004"
    # Playwright targets the raw embed form, not the (possibly iframed) listing.
    assert job.application_url == (
        "https://boards.greenhouse.io/embed/job_app?for=figma&token=5364702004"
    )
    assert job.description == "Build with Python"
    assert job.tags == ["Engineering"]


def test_rank_orders_by_relevance():
    jobs = [
        Job(id="1", title="Marketing Lead", company="A", url="u1", tags=["marketing"]),
        Job(id="2", title="Python Engineer", company="B", url="u2", tags=["python", "aws"]),
    ]
    ranked = _rank(jobs, "python aws backend", limit=2)
    assert ranked[0].id == "2"  # most relevant first


def test_rank_keeps_order_when_no_match():
    jobs = [Job(id="1", title="Chef", company="A", url="u1")]
    assert _rank(jobs, "python", limit=5) == jobs


def test_build_search_provider_remoteok():
    provider = build_search_provider(Settings(_env_file=None, search_provider="remoteok"))
    assert isinstance(provider, RemoteOKJobSearchProvider)


def test_remoteok_to_job_mapping():
    item = {
        "id": "999",
        "position": "Backend Engineer",
        "company": "Globex",
        "location": "Worldwide",
        "url": "https://remoteok.com/remote-jobs/999",
        "apply_url": "https://globex.com/apply",
        "description": "<p>Python &amp; Go</p>",
        "tags": ["python", "go"],
        "salary_min": 120000,
        "salary_max": 160000,
        "date": "2026-07-01",
    }
    job = RemoteOKJobSearchProvider._to_job(item)
    assert job.title == "Backend Engineer"
    assert job.company == "Globex"
    assert job.source == "remoteok"
    assert job.application_url == "https://globex.com/apply"
    assert "<" not in job.description
    assert job.salary == "$120,000–$160,000"


def test_build_search_provider_remotive():
    provider = build_search_provider(Settings(_env_file=None, search_provider="remotive"))
    assert isinstance(provider, RemotiveJobSearchProvider)


def test_remotive_to_job_mapping():
    item = {
        "id": 123,
        "title": "Senior Python Engineer",
        "company_name": "Acme Remote",
        "candidate_required_location": "Worldwide",
        "url": "https://remotive.com/remote-jobs/123",
        "description": "<p>Build <b>APIs</b> with Python &amp; FastAPI.</p>",
        "tags": ["python", "fastapi"],
        "publication_date": "2026-07-01",
        "salary": "$150k",
    }
    job = RemotiveJobSearchProvider._to_job(item)
    assert job.id == "123"
    assert job.company == "Acme Remote"
    assert job.remote is True
    assert job.source == "remotive"
    assert "<" not in job.description  # HTML stripped
    assert "FastAPI" in job.description
    assert job.application_url == "https://remotive.com/remote-jobs/123"


def test_remote_to_job_mapping():
    item = {
        "id": 42,
        "title": "Backend Engineer",
        "company_name": "Globex",
        "candidate_required_location": "Remote",
        "url": "https://globex/apply",
        "description": "Build things",
        "tags": ["python"],
    }
    job = RemoteJobSearchProvider._to_job(item)
    assert job.id == "42"
    assert job.company == "Globex"
    assert job.location == "Remote"
    assert job.source == "remote"
