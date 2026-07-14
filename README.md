# JobPilot 🚀

**An AI job-application agent that searches for jobs, tailors your resume and cover
letter, fills the application form — and always stops for your approval before
anything is submitted.**

JobPilot is a modular, multi-agent system built on **LangGraph**, **Playwright**,
**FastAPI**, and a **configurable LLM** (Anthropic Claude by default). Eight focused
agents collaborate over a single graph, with a human-in-the-loop breakpoint that
makes submission a deliberate, explicit act.

> **Safety first.** JobPilot never submits an application on its own. Every run
> pauses after drafting so a human can review the resume, cover letter and the
> exact form values, then approve or reject. A second setting
> (`browser_allow_submit`) can disable submission entirely.

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [How a run flows](#how-a-run-flows)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Using the CLI](#using-the-cli)
- [Using the HTTP API](#using-the-http-api)
- [Configurable LLM](#configurable-llm)
- [Job-search & browser back-ends](#job-search--browser-back-ends)
- [Project layout](#project-layout)
- [Development](#development)
- [Docker](#docker)
- [Responsible use](#responsible-use)
- [License](#license)

---

## Features

- **Multi-agent architecture** — Planner, Search, Job Analyzer, Resume, Cover
  Letter, Application, Reviewer, and Summarizer, each a small, testable unit.
- **LangGraph orchestration** — a checkpointed state graph with conditional
  routing and a real human-in-the-loop breakpoint (pause → approve → resume).
- **Tailored documents** — a resume rewritten to emphasise relevant experience
  (never fabricated) and a matching cover letter.
- **Playwright form automation** — detects and fills real application forms;
  captures a screenshot/HTML preview so you review before you submit.
- **Runs fully offline** — with no API key the agents fall back to deterministic
  heuristics, so the whole pipeline is demoable and testable without a browser,
  network, or model credits. Add a key to switch to LLM-quality output.
- **Configurable LLM** — Anthropic Claude (`claude-opus-4-8`) by default; OpenAI
  available via an optional extra. Provider is a one-line setting.
- **Production niceties** — structured logging (structlog), typed settings
  (pydantic-settings), a clean REST API, a friendly CLI, Docker support, and a
  test suite (58 tests) that runs without any external service.

## Architecture

Eight agents are wired into one LangGraph `StateGraph`. Shared state is a typed
dict of rich Pydantic models; list fields accumulate via reducers.

```
                            ┌─────────┐
        START ─────────────▶│ Planner │  goal + profile → plan + search query
                            └────┬────┘
                                 ▼
                            ┌─────────┐
                            │ Search  │  find & rank jobs
                            └────┬────┘
                    no jobs ┌────┴────┐ jobs
              ┌─────────────┘         └─────────────┐
              ▼                                      ▼
        ┌──────────┐                          ┌──────────────┐
        │Summarizer│◀────────────┐            │ Job Analyzer │  score vs. resume
        └────┬─────┘             │            └──────┬───────┘
             ▼                   │                   ▼
            END                  │            ┌──────────────┐
                                 │            │    Resume    │  tailor resume
                                 │            └──────┬───────┘
                                 │                   ▼
                                 │            ┌──────────────┐
                                 │            │ Cover Letter │
                                 │            └──────┬───────┘
                                 │                   ▼
                                 │            ┌──────────────┐
                                 │            │ Application  │  fill form (no submit)
                                 │            │   .fill()    │
                                 │            └──────┬───────┘
                                 │                   ▼
                                 │            ┌──────────────┐
                                 │            │   Reviewer   │  quality gate
                                 │            └──────┬───────┘
                                 │                   ▼
                                 │        🔶 INTERRUPT: human approval
                                 │                   ▼
                                 │            ┌──────────────┐
                                 │  rejected  │ approval_gate│
                                 └────────────┴──────┬───────┘
                                                     │ approved
                                                     ▼
                                              ┌──────────────┐
                                              │ Application  │  submit
                                              │  .submit()   │
                                              └──────┬───────┘
                                                     ▼
                                               (→ Summarizer → END)
```

| Agent | Responsibility |
|-------|----------------|
| **Planner** | Turns the candidate profile + free-text goal into a target role, a search query, and a step plan. |
| **Search** | Runs the query against a job-search provider and selects the best-ranked posting. |
| **Job Analyzer** | Scores the posting against the resume; extracts matched/missing skills, requirements, and a recommendation. |
| **Resume** | Produces a tailored resume (headline, summary, reprioritised skills, relevant highlights) as Markdown. |
| **Cover Letter** | Writes a focused, company-specific cover letter. |
| **Application** | Uses Playwright to detect & fill the form (`fill`) and, only after approval, to submit it (`submit`). |
| **Reviewer** | Automated quality gate: verdict, score, checklist, issues, suggestions. |
| **Summarizer** | Briefs the candidate on what happened and the next steps. |

## How a run flows

1. **Start** a run with a candidate profile and a goal (CLI or `POST /applications`).
2. Agents **plan → search → analyse → draft resume → draft cover letter → fill form → review**.
3. The graph **pauses** at the approval breakpoint. State (drafts + filled form + review) is returned to you.
4. You **approve or reject** (`POST /applications/{id}/approve`).
5. On approval the **Application agent submits**; either way the **Summarizer** writes a closing brief.

Generated artefacts (resume, cover letter, form preview screenshot/HTML) are written
under `artifacts/<job-id>/`.

## Quickstart

Requires **Python 3.11+**.

```bash
# 1. Install (editable, with dev tools)
python -m venv .venv
source .venv/Scripts/activate        # Windows: .venv\Scripts\activate  |  *nix: source .venv/bin/activate
pip install -e ".[dev]"

# 2. (Optional) install the Chromium browser for live form filling
python -m playwright install chromium

# 3. Run a full application from the CLI using the bundled sample profile
jobpilot run --candidate data/sample_candidate.json --goal "Senior Python engineer, remote"
```

No API key? It just works in **heuristic mode**. To use a real model, set a key
(see below) and JobPilot switches to LLM-quality drafting automatically.

> Using `make`? `make dev` installs everything (incl. the browser); `make cli`
> runs the sample; `make run` starts the API; `make test` runs the suite.

## Configuration

All settings are environment variables (prefixed `JOBPILOT_`) and/or a `.env`
file. Copy the template and edit:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `JOBPILOT_LLM_PROVIDER` | `anthropic` | `anthropic` or `openai`. |
| `JOBPILOT_LLM_MODEL` | `claude-opus-4-8` | Model id for the provider. |
| `JOBPILOT_LLM_MAX_TOKENS` | `4096` | Max output tokens per call. |
| `JOBPILOT_LLM_TEMPERATURE` | *(unset)* | Sampling temperature; omit for models that reject it. |
| `JOBPILOT_LLM_BASE_URL` | *(unset)* | Custom OpenAI-compatible endpoint (OpenRouter, DeepSeek, local server). Used only when provider is `openai`. |
| `ANTHROPIC_API_KEY` | *(unset)* | Enables Claude. Without it, agents run heuristically. |
| `OPENAI_API_KEY` | *(unset)* | Enables OpenAI (requires the `openai` extra). |
| `JOBPILOT_SEARCH_PROVIDER` | `sample` | `sample` (offline), `greenhouse`/`remoteok`/`remotive` (real, free), or `remote` (your API). |
| `JOBPILOT_GREENHOUSE_COMPANIES` | *(10 tech cos)* | Comma-separated Greenhouse board slugs to search (provider `greenhouse`). |
| `JOBPILOT_SEARCH_API_URL` / `_API_KEY` | *(unset)* | For the `remote` provider. |
| `JOBPILOT_MAX_JOBS` | `5` | Max jobs to fetch per search. |
| `JOBPILOT_BROWSER_MODE` | `auto` | `auto`, `playwright`, or `simulated`. |
| `JOBPILOT_BROWSER_HEADLESS` | `true` | Run Chromium headless. |
| `JOBPILOT_BROWSER_ALLOW_SUBMIT` | `true` | Master switch; `false` disables submission entirely. |
| `JOBPILOT_ARTIFACTS_DIR` | `artifacts` | Where drafts and previews are written. |
| `JOBPILOT_LOG_LEVEL` | `INFO` | Logging level. |
| `JOBPILOT_LOG_FORMAT` | `console` | `console` (dev) or `json` (production). |

## Using the CLI

```bash
# Interactive: prints the drafts, then prompts y/N to approve submission
jobpilot run --candidate data/sample_candidate.json --goal "Senior Python engineer"

# Non-interactive
jobpilot run --candidate cv.json --goal "ML engineer, remote" --approve   # auto-approve
jobpilot run --candidate cv.json --goal "ML engineer, remote" --reject    # draft only

# Start the API server
jobpilot serve --port 8000

jobpilot version
```

The candidate file is JSON matching the `CandidateProfile` schema — see
[`data/sample_candidate.json`](data/sample_candidate.json).

## Using the HTTP API

Start it: `uvicorn jobpilot.main:app --reload` (interactive docs at `/docs`).

```bash
# 1. Start a run (drafts everything, pauses for approval)
curl -s -X POST localhost:8000/applications \
  -H 'content-type: application/json' \
  -d '{"candidate": '"$(cat data/sample_candidate.json)"', "goal": "Senior Python engineer, remote"}'
# -> 201 { "thread_id": "...", "status": "awaiting_approval", "resume": {...}, "review": {...}, ... }

# 2. Inspect the paused run
curl -s localhost:8000/applications/<thread_id>

# 3. Approve (submit) or reject
curl -s -X POST localhost:8000/applications/<thread_id>/approve \
  -H 'content-type: application/json' -d '{"approved": true}'
```

| Method & path | Purpose |
|---------------|---------|
| `GET /health` | Liveness + effective config. |
| `POST /applications` | Start a run; executes to the approval breakpoint. |
| `GET /applications/{thread_id}` | Fetch current state (drafts, form, review). |
| `POST /applications/{thread_id}/approve` | Approve/reject and resume to completion. |

`approve` accepts optional `notes` and `field_overrides` (per-field values keyed
by the form field's selector) so you can correct any answer before submitting.

## Configurable LLM

JobPilot talks to models through LangChain's `BaseChatModel`, so agents are
provider-agnostic. The factory ([`llm.py`](src/jobpilot/llm.py)) is lazy —
provider SDKs are imported only when selected.

- **Anthropic (default & recommended):** `claude-opus-4-8`, ships in the base install.
- **OpenAI (optional):** `pip install ".[openai]"` and set
  `JOBPILOT_LLM_PROVIDER=openai`, `JOBPILOT_LLM_MODEL=...`, `OPENAI_API_KEY=...`.
- **Any OpenAI-compatible endpoint** (OpenRouter, DeepSeek, Together, Groq, a
  local server): use the `openai` provider and set `JOBPILOT_LLM_BASE_URL`. For
  example, DeepSeek via OpenRouter:

  ```env
  JOBPILOT_LLM_PROVIDER=openai
  JOBPILOT_LLM_MODEL=deepseek/deepseek-chat
  JOBPILOT_LLM_BASE_URL=https://openrouter.ai/api/v1
  OPENAI_API_KEY=sk-or-v1-...
  ```

If no key is configured for the active provider, every agent uses a deterministic
heuristic implementation instead — the pipeline still runs start-to-finish.

## Job-search & browser back-ends

**Job search** ([`tools/job_search.py`](src/jobpilot/tools/job_search.py)) — set `JOBPILOT_SEARCH_PROVIDER`:

- `greenhouse` — **real jobs with directly-fillable application forms.** Searches
  the public [Greenhouse](https://greenhouse.io) boards of the companies in
  `JOBPILOT_GREENHOUSE_COMPANIES`. This is the provider to use with live
  Playwright form-filling (see below).
- `remoteok` — **real** tech jobs from the free, no-auth [RemoteOK](https://remoteok.com) API.
- `remotive` — **real** remote jobs from the free, no-auth [Remotive](https://remotive.com) API.
- `sample` — a small in-memory corpus of realistic postings; zero setup (default, offline).
- `remote` — an HTTP client you point at any other JSON job board. Adapt
  `RemoteJobSearchProvider._to_job` to the provider's response shape.

> These free APIs don't filter reliably server-side, so JobPilot fetches a pool
> and ranks it **client-side** by relevance to your keywords. Match quality
> depends on what's currently posted. `remoteok`/`remotive` are aggregators whose
> "apply" links redirect to third-party ATSs, so they're best for *discovery*;
> `greenhouse` gives the actual form URL, which is what Playwright can fill.

**Browser** ([`tools/browser.py`](src/jobpilot/tools/browser.py)):

- `simulated` — fabricates a standard application form and fills it offline
  (no browser). Great for demos, tests, and the sample jobs.
- `playwright` — drives real Chromium: detects fields, fills them, screenshots,
  and (only after approval) clicks submit.
- `auto` (default) — Playwright for live `http(s)` forms when available, simulated otherwise.

### Applying to real jobs with Playwright

1. `pip install -e ".[dev,openai]"` then `python -m playwright install chromium`.
2. In `.env`: `JOBPILOT_SEARCH_PROVIDER=greenhouse`, `JOBPILOT_BROWSER_MODE=auto`
   (and `JOBPILOT_BROWSER_HEADLESS=false` to watch it work).
3. Run a search + application; JobPilot opens the real Greenhouse form, fills the
   standard fields from your profile (name, email, phone, LinkedIn, résumé upload,
   cover letter), screenshots it, and **pauses for your approval**.

> **What it does and doesn't do.** JobPilot reliably fills the *standard* fields.
> Employer-specific questions — work authorization, "How did you hear about us?",
> EEO/demographic questions, essay prompts, dropdowns — are **left for you** and
> flagged by the Reviewer. Nothing is submitted until you approve, and you can
> correct any field via `field_overrides` on the approval call. Some ATSs (and
> CAPTCHAs / logins) can't be automated at all; automating submissions may also
> conflict with a site's Terms of Service — that's your call, per application.

## Project layout

```
src/jobpilot/
├── config.py            # Typed settings (pydantic-settings)
├── logging_config.py    # Structured logging (structlog)
├── llm.py               # Configurable LLM factory
├── serialization.py     # Checkpoint serializer (allow-lists our types)
├── schemas/             # Pydantic domain models + LangGraph state (TypedDict)
├── tools/
│   ├── job_search.py    # Sample + remote job providers
│   └── browser.py       # Field mapping + simulated/Playwright fillers
├── agents/              # The 8 agents + prompt templates + base class
├── graph.py             # StateGraph assembly + approval breakpoint
├── orchestrator.py      # Run lifecycle (start / status / approve)
├── api/                 # FastAPI app, routes, request/response models
├── cli.py               # `jobpilot` command
└── main.py              # ASGI entrypoint (uvicorn jobpilot.main:app)
tests/                   # 58 tests, run fully offline
data/                    # Sample candidate profile
```

## Development

```bash
make test        # pytest (offline; no keys or browser needed)
make test-cov    # with coverage
make lint        # ruff
make typecheck   # mypy
make format      # ruff format + autofix
```

- Tests run entirely offline (heuristic agents + simulated browser).
- Agents inject their LLM, search provider, and form-filler, so every path is
  testable with fakes. See [`tests/conftest.py`](tests/conftest.py).
- Live-browser tests are intentionally omitted from the default run; the
  Playwright paths are exercised manually or in a browser-provisioned CI job.

## Docker

```bash
# Build (installs the package + Chromium + OS deps)
docker build -t jobpilot:latest .

# Run the API (reads .env for ANTHROPIC_API_KEY etc.)
docker compose up --build      # -> http://localhost:8000/docs
```

The image runs as a non-root user, logs JSON, and mounts `./artifacts` so
generated documents persist on the host.

## Responsible use

JobPilot is a productivity tool for **your own** job search. Please:

- **Review every draft.** LLM output can be wrong; the resume/cover letter are
  starting points. The mandatory approval step exists for exactly this reason.
- **Never fabricate.** The Resume agent is instructed to only rephrase and
  reprioritise real experience — keep it that way.
- **Respect each site's Terms of Service** and rate limits when enabling live
  Playwright submission. Automating form submission may be disallowed by some
  job boards; that responsibility is yours.
- **Handle personal data carefully.** Candidate profiles and generated documents
  may contain PII; the artifacts directory is git-ignored by default.

## License

[MIT](LICENSE) © 2026 JobPilot Contributors.
