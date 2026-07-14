"""Pluggable job-search providers.

Three providers ship with JobPilot:

* :class:`SampleJobSearchProvider` — offline fixtures so the whole pipeline runs
  out of the box with no API keys or network. This is the default.
* :class:`RemotiveJobSearchProvider` — real remote jobs from the free, no-auth
  Remotive API (https://remotive.com). Set ``JOBPILOT_SEARCH_PROVIDER=remotive``.
* :class:`RemoteJobSearchProvider` — a thin HTTP client you point at any other
  job board. The response mapping is deliberately generic; adapt
  :meth:`RemoteJobSearchProvider._to_job` to your provider's schema.
"""

from __future__ import annotations

import asyncio
import html
import re
from abc import ABC, abstractmethod

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from jobpilot.config import Settings, get_settings
from jobpilot.logging_config import get_logger
from jobpilot.schemas.job import Job, JobSearchQuery

logger = get_logger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Strip HTML to plain text.

    Handles both real markup and entity-encoded markup (Greenhouse double-encodes
    its ``content`` field), so we unescape, remove tags, then unescape again.
    """
    text = html.unescape(text)
    text = _TAG_RE.sub(" ", text)
    return html.unescape(text).replace("\xa0", " ").strip()


# A small, self-contained corpus so the demo works entirely offline.
_SAMPLE_JOBS: list[dict] = [
    {
        "id": "sample-py-001",
        "title": "Senior Python Engineer",
        "company": "Northwind Labs",
        "location": "Remote (US)",
        "remote": True,
        "url": "https://example.com/jobs/senior-python-engineer",
        "apply_url": "https://example.com/jobs/senior-python-engineer/apply",
        "salary": "$150k–$185k",
        "posted_at": "2026-07-01",
        "source": "sample",
        "tags": ["python", "backend", "aws", "fastapi", "postgresql"],
        "description": (
            "We are hiring a Senior Python Engineer to design and build backend "
            "services. You will own REST APIs with FastAPI, work with PostgreSQL, "
            "and deploy to AWS. Requirements: 5+ years of Python, strong experience "
            "with FastAPI or Flask, relational databases, Docker, and CI/CD. Bonus: "
            "async programming, Kubernetes, and event-driven architectures."
        ),
    },
    {
        "id": "sample-ml-002",
        "title": "Machine Learning Engineer",
        "company": "Vertex AI Systems",
        "location": "New York, NY",
        "remote": False,
        "url": "https://example.com/jobs/ml-engineer",
        "apply_url": "https://example.com/jobs/ml-engineer/apply",
        "salary": "$160k–$200k",
        "posted_at": "2026-06-28",
        "source": "sample",
        "tags": ["python", "pytorch", "ml", "nlp", "llm"],
        "description": (
            "Join our ML platform team to ship models to production. You will build "
            "training and inference pipelines, fine-tune LLMs, and optimise serving. "
            "Requirements: 3+ years in ML engineering, Python, PyTorch, and MLOps "
            "tooling. Experience with LLMs, vector databases, and Kubernetes preferred."
        ),
    },
    {
        "id": "sample-fs-003",
        "title": "Full-Stack Software Engineer",
        "company": "BrightForge",
        "location": "Remote (Global)",
        "remote": True,
        "url": "https://example.com/jobs/full-stack-engineer",
        "apply_url": "https://example.com/jobs/full-stack-engineer/apply",
        "salary": "$120k–$160k",
        "posted_at": "2026-07-05",
        "source": "sample",
        "tags": ["typescript", "react", "python", "node", "fullstack"],
        "description": (
            "We need a Full-Stack Engineer comfortable across the stack. Frontend in "
            "React/TypeScript, backend in Python or Node. Requirements: 4+ years "
            "building web apps, solid JavaScript/TypeScript, REST APIs, and testing. "
            "Nice to have: GraphQL, AWS, and design-system experience."
        ),
    },
    {
        "id": "sample-de-004",
        "title": "Data Engineer",
        "company": "Cloudstream Analytics",
        "location": "Austin, TX (Hybrid)",
        "remote": False,
        "url": "https://example.com/jobs/data-engineer",
        "apply_url": "https://example.com/jobs/data-engineer/apply",
        "salary": "$135k–$170k",
        "posted_at": "2026-06-20",
        "source": "sample",
        "tags": ["python", "sql", "spark", "airflow", "data"],
        "description": (
            "Build and maintain data pipelines that power analytics. Requirements: "
            "Python, advanced SQL, Apache Spark, and orchestration with Airflow. "
            "Experience with dbt, Snowflake, and streaming (Kafka) is a plus."
        ),
    },
    {
        "id": "sample-devops-005",
        "title": "DevOps / Platform Engineer",
        "company": "Helios Cloud",
        "location": "Remote (EU)",
        "remote": True,
        "url": "https://example.com/jobs/platform-engineer",
        "apply_url": "https://example.com/jobs/platform-engineer/apply",
        "salary": "€90k–€120k",
        "posted_at": "2026-07-10",
        "source": "sample",
        "tags": ["kubernetes", "terraform", "aws", "ci-cd", "python"],
        "description": (
            "Own our cloud platform and developer experience. Requirements: strong "
            "Kubernetes, Terraform, AWS, and CI/CD pipelines. Scripting in Python or "
            "Go. Observability (Prometheus/Grafana) and security best-practices "
            "experience valued."
        ),
    },
]


class JobSearchProvider(ABC):
    """Abstract base class for job-search back-ends."""

    name: str = "abstract"

    @abstractmethod
    async def search(self, query: JobSearchQuery) -> list[Job]:
        """Return jobs matching ``query`` (already truncated to ``query.limit``)."""
        raise NotImplementedError


def _score(job: Job, terms: list[str]) -> int:
    """Count how many query terms appear in the job's searchable text."""
    haystack = " ".join(
        [job.title, job.company, job.description, " ".join(job.tags), job.location or ""]
    ).lower()
    return sum(1 for term in terms if term and term in haystack)


def _rank(jobs: list[Job], keywords: str, limit: int) -> list[Job]:
    """Rank a pool of jobs by keyword relevance, client-side.

    The free job APIs we use return a recent pool but do not filter reliably on
    a search term, so we rank locally. If nothing matches, recency order is kept.
    """
    terms = [t for t in keywords.lower().replace(",", " ").split() if len(t) > 1]
    if not terms:
        return jobs[:limit]
    ranked = sorted(jobs, key=lambda j: _score(j, terms), reverse=True)
    if not ranked or _score(ranked[0], terms) == 0:
        return jobs[:limit]
    return ranked[:limit]


class SampleJobSearchProvider(JobSearchProvider):
    """Offline provider backed by an in-memory corpus of realistic postings."""

    name = "sample"

    def __init__(self, jobs: list[dict] | None = None) -> None:
        self._jobs = [Job(**data) for data in (jobs or _SAMPLE_JOBS)]

    async def search(self, query: JobSearchQuery) -> list[Job]:
        terms = [t for t in query.keywords.lower().replace(",", " ").split() if len(t) > 1]

        candidates = self._jobs
        if query.remote is True:
            candidates = [j for j in candidates if j.remote]
        if query.location:
            loc = query.location.lower()
            candidates = [
                j for j in candidates if j.remote or (j.location and loc in j.location.lower())
            ]

        ranked = sorted(candidates, key=lambda j: _score(j, terms), reverse=True)
        # If nothing matched any term, still return the corpus (best-effort).
        if terms and ranked and _score(ranked[0], terms) == 0:
            ranked = candidates

        results = ranked[: query.limit]
        logger.info("job_search.sample", terms=terms, returned=len(results))
        return results


class RemoteJobSearchProvider(JobSearchProvider):
    """HTTP job-search provider.

    Point it at any JSON job-search API. Override :meth:`_to_job` to map the
    provider's response shape onto :class:`~jobpilot.schemas.job.Job`.
    """

    name = "remote"

    def __init__(self, api_url: str, api_key: str | None = None, timeout: float = 20.0) -> None:
        if not api_url:
            raise ValueError("RemoteJobSearchProvider requires a non-empty api_url")
        self._api_url = api_url
        self._api_key = api_key
        self._timeout = timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    async def _get(self, params: dict) -> dict:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(self._api_url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _to_job(item: dict) -> Job:
        """Best-effort mapping from a generic API item to a :class:`Job`."""
        return Job(
            id=str(item.get("id") or item.get("job_id") or item.get("slug") or item.get("url")),
            title=item.get("title") or item.get("position") or "Unknown role",
            company=item.get("company") or item.get("company_name") or "Unknown company",
            location=item.get("location") or item.get("candidate_required_location"),
            remote=bool(item.get("remote", False)),
            url=item.get("url") or item.get("apply_url") or "",
            apply_url=item.get("apply_url"),
            description=item.get("description") or item.get("snippet") or "",
            salary=item.get("salary"),
            posted_at=item.get("posted_at") or item.get("date"),
            source="remote",
            tags=item.get("tags") or [],
        )

    async def search(self, query: JobSearchQuery) -> list[Job]:
        params = {"q": query.keywords, "limit": query.limit}
        if query.location:
            params["location"] = query.location
        if query.remote is not None:
            params["remote"] = str(query.remote).lower()

        payload = await self._get(params)
        items = payload.get("jobs") or payload.get("results") or payload.get("data") or []
        jobs = [self._to_job(item) for item in items][: query.limit]
        logger.info("job_search.remote", returned=len(jobs), url=self._api_url)
        return jobs


class RemotiveJobSearchProvider(JobSearchProvider):
    """Real remote jobs from the free, no-auth Remotive API.

    Docs: https://github.com/remotive-com/remote-jobs-api. No API key required.
    """

    name = "remotive"
    BASE_URL = "https://remotive.com/api/remote-jobs"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    async def _get(self, params: dict) -> dict:
        headers = {"User-Agent": "JobPilot/0.1 (+https://github.com/your-org/jobpilot)"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(self.BASE_URL, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _to_job(item: dict) -> Job:
        return Job(
            id=str(item.get("id")),
            title=item.get("title") or "Unknown role",
            company=item.get("company_name") or "Unknown company",
            location=item.get("candidate_required_location") or "Remote",
            remote=True,
            url=item.get("url") or "",
            apply_url=item.get("url"),
            description=strip_html(item.get("description") or "")[:5000],
            salary=item.get("salary") or None,
            posted_at=item.get("publication_date"),
            source="remotive",
            tags=item.get("tags") or [],
        )

    async def search(self, query: JobSearchQuery) -> list[Job]:
        # Remotive's `search` param is unreliable, so fetch a pool and rank locally.
        payload = await self._get({"limit": 100})
        jobs = [self._to_job(item) for item in payload.get("jobs") or []]
        ranked = _rank(jobs, query.keywords, query.limit)
        logger.info(
            "job_search.remotive", terms=query.keywords, pool=len(jobs), returned=len(ranked)
        )
        return ranked


class RemoteOKJobSearchProvider(JobSearchProvider):
    """Real, tech-focused remote jobs from the free, no-auth RemoteOK API.

    RemoteOK returns ~100 recent postings (the first element is legal metadata).
    It does not filter server-side, so results are ranked client-side.
    """

    name = "remoteok"
    BASE_URL = "https://remoteok.com/api"

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    async def _get(self) -> list:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JobPilot/0.1)"}
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            resp = await client.get(self.BASE_URL, headers=headers)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _to_job(item: dict) -> Job:
        salary = None
        if item.get("salary_min") and item.get("salary_max"):
            salary = f"${item['salary_min']:,}–${item['salary_max']:,}"
        return Job(
            id=str(item.get("id") or item.get("slug")),
            title=item.get("position") or item.get("title") or "Unknown role",
            company=item.get("company") or "Unknown company",
            location=item.get("location") or "Remote",
            remote=True,
            url=item.get("url") or "",
            apply_url=item.get("apply_url") or item.get("url"),
            description=strip_html(item.get("description") or "")[:5000],
            salary=salary,
            posted_at=item.get("date"),
            source="remoteok",
            tags=[str(t) for t in (item.get("tags") or [])],
        )

    async def search(self, query: JobSearchQuery) -> list[Job]:
        data = await self._get()
        items = [x for x in data if isinstance(x, dict) and (x.get("position") or x.get("slug"))]
        jobs = [self._to_job(item) for item in items]
        ranked = _rank(jobs, query.keywords, query.limit)
        logger.info(
            "job_search.remoteok", terms=query.keywords, pool=len(jobs), returned=len(ranked)
        )
        return ranked


class GreenhouseJobSearchProvider(JobSearchProvider):
    """Real jobs with **direct, fillable application forms** from Greenhouse boards.

    Greenhouse hosts a standard application form at each job's ``absolute_url``
    (first name, last name, email, phone, resume upload, cover letter, ...), which
    is exactly what the Playwright form-filler can complete. Boards are per-company,
    so configure the slugs via ``JOBPILOT_GREENHOUSE_COMPANIES``.
    """

    name = "greenhouse"
    API = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"

    def __init__(self, companies: list[str], timeout: float = 20.0) -> None:
        self.companies = [c.strip() for c in companies if c.strip()]
        self._timeout = timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    async def _get_company(self, client: httpx.AsyncClient, company: str) -> tuple[str, list]:
        resp = await client.get(self.API.format(company=company), params={"content": "true"})
        resp.raise_for_status()
        return company, resp.json().get("jobs", [])

    #: Greenhouse serves the raw, inline application form here (no iframe/cookie
    #: banner), which is what Playwright can actually fill. The company's own
    #: ``absolute_url`` often embeds the form in an iframe, so we target this.
    EMBED_URL = "https://boards.greenhouse.io/embed/job_app?for={company}&token={token}"

    @classmethod
    def _to_job(cls, item: dict, company: str) -> Job:
        location = (item.get("location") or {}).get("name") or "See posting"
        job_id = str(item.get("id"))
        return Job(
            id=job_id,
            title=item.get("title") or "Unknown role",
            company=company.replace("-", " ").title(),
            location=location,
            remote="remote" in location.lower(),
            url=item.get("absolute_url") or "",
            apply_url=cls.EMBED_URL.format(company=company, token=job_id),
            description=strip_html(item.get("content") or "")[:5000],
            posted_at=item.get("updated_at"),
            source="greenhouse",
            tags=[d.get("name") for d in (item.get("departments") or []) if d.get("name")],
        )

    async def search(self, query: JobSearchQuery) -> list[Job]:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JobPilot/0.1)"}
        async with httpx.AsyncClient(timeout=self._timeout, headers=headers) as client:
            results = await asyncio.gather(
                *(self._get_company(client, c) for c in self.companies),
                return_exceptions=True,
            )
        jobs: list[Job] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("job_search.greenhouse.company_failed", error=str(result))
                continue
            company, items = result
            jobs.extend(self._to_job(item, company) for item in items)
        ranked = _rank(jobs, query.keywords, query.limit)
        logger.info(
            "job_search.greenhouse",
            companies=len(self.companies),
            pool=len(jobs),
            returned=len(ranked),
        )
        return ranked


def build_search_provider(settings: Settings | None = None) -> JobSearchProvider:
    """Construct the configured job-search provider."""
    settings = settings or get_settings()
    if settings.search_provider == "greenhouse":
        return GreenhouseJobSearchProvider(settings.greenhouse_companies.split(","))
    if settings.search_provider == "remoteok":
        return RemoteOKJobSearchProvider()
    if settings.search_provider == "remotive":
        return RemotiveJobSearchProvider()
    if settings.search_provider == "remote":
        if not settings.search_api_url:
            raise ValueError("search_provider='remote' requires JOBPILOT_SEARCH_API_URL to be set")
        return RemoteJobSearchProvider(settings.search_api_url, settings.search_api_key)
    return SampleJobSearchProvider()
