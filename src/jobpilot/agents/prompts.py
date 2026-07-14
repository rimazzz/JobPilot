"""System prompts and user-message builders for the LLM-backed agents.

Prompts are kept together so they are easy to review and iterate on. Each agent
pairs a stable ``*_SYSTEM`` instruction with a ``build_*_user`` function that
renders the current run state into a concise, structured message.
"""

from __future__ import annotations

from jobpilot.schemas.candidate import CandidateProfile
from jobpilot.schemas.documents import CoverLetter, JobAnalysis, TailoredResume
from jobpilot.schemas.job import Job

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _candidate_brief(candidate: CandidateProfile) -> str:
    exp_lines = []
    for exp in candidate.experiences:
        period = f"{exp.start_date or '?'}–{exp.end_date or 'Present'}"
        exp_lines.append(f"- {exp.title} @ {exp.company} ({period})")
        for hl in exp.highlights[:4]:
            exp_lines.append(f"    • {hl}")
    education = "; ".join(
        f"{e.degree or ''} {e.field_of_study or ''} @ {e.institution}".strip()
        for e in candidate.education
    )
    return (
        f"Name: {candidate.full_name}\n"
        f"Headline: {candidate.headline or 'n/a'}\n"
        f"Location: {candidate.location or 'n/a'} | Open to remote: {candidate.open_to_remote}\n"
        f"Years experience: {candidate.years_experience or 'n/a'}\n"
        f"Summary: {candidate.summary or 'n/a'}\n"
        f"Skills: {candidate.skills_text() or 'n/a'}\n"
        f"Experience:\n" + ("\n".join(exp_lines) or "  (none listed)") + "\n"
        f"Education: {education or 'n/a'}"
    )


def _job_brief(job: Job) -> str:
    return (
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location or 'n/a'} | Remote: {job.remote}\n"
        f"Tags: {', '.join(job.tags) or 'n/a'}\n"
        f"Description:\n{job.description}"
    )


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

PLANNER_SYSTEM = (
    "You are the Planner in a multi-agent job-application system. Given a "
    "candidate profile and a free-text goal, produce a concise plan and the "
    "parameters for a job search. Choose a single, specific target role and "
    "search keywords that will surface relevant postings. Be realistic and "
    "specific; do not invent facts about the candidate."
)


def build_planner_user(candidate: CandidateProfile, goal: str) -> str:
    return (
        f"CANDIDATE\n{_candidate_brief(candidate)}\n\n"
        f"GOAL\n{goal}\n\n"
        "Produce the target role, search keywords, optional location/seniority, "
        "whether to restrict to remote, a one-line objective, an ordered list of "
        "plan steps, and any notes."
    )


# ---------------------------------------------------------------------------
# Job Analyzer
# ---------------------------------------------------------------------------

ANALYZER_SYSTEM = (
    "You are the Job Analyzer. Compare a job description against a candidate and "
    "produce an objective assessment: a 0–100 match score, the key requirements, "
    "which of the candidate's skills match, which required skills are missing, "
    "important keywords for ATS, concrete strengths and gaps, and an overall "
    "recommendation (apply / maybe / skip). Be honest about gaps."
)


def build_analyzer_user(candidate: CandidateProfile, job: Job) -> str:
    return f"CANDIDATE\n{_candidate_brief(candidate)}\n\nJOB\n{_job_brief(job)}"


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

RESUME_SYSTEM = (
    "You are the Resume writer. Tailor the candidate's existing experience to a "
    "specific job. Write a crisp professional headline, a 2–3 sentence summary "
    "targeted at the role, an ordered list of the most relevant skills (lead with "
    "the ones the job asks for), and 4–6 achievement-oriented experience bullets "
    "rewritten to emphasise relevance. STRICT RULE: never fabricate employers, "
    "titles, dates, degrees, or accomplishments — only rephrase and reprioritise "
    "what the candidate already provided. List the tailoring changes you made."
)


def build_resume_user(candidate: CandidateProfile, job: Job, analysis: JobAnalysis) -> str:
    return (
        f"CANDIDATE\n{_candidate_brief(candidate)}\n\n"
        f"JOB\n{_job_brief(job)}\n\n"
        f"ANALYSIS\nMatched skills: {', '.join(analysis.matched_skills) or 'n/a'}\n"
        f"Missing skills: {', '.join(analysis.missing_skills) or 'n/a'}\n"
        f"Keywords: {', '.join(analysis.keywords) or 'n/a'}"
    )


# ---------------------------------------------------------------------------
# Cover Letter
# ---------------------------------------------------------------------------

COVER_LETTER_SYSTEM = (
    "You are the Cover Letter writer. Write a focused, genuine cover letter body "
    "of 3–4 short paragraphs (180–320 words). Open with specific interest in the "
    "company and role, connect the candidate's real, relevant experience to the "
    "job's needs, and close with a confident call to action. Warm and "
    "professional; no clichés, no fabrication, no placeholders like [Company]."
)


def build_cover_letter_user(candidate: CandidateProfile, job: Job, analysis: JobAnalysis) -> str:
    return (
        f"CANDIDATE\n{_candidate_brief(candidate)}\n\n"
        f"JOB\n{_job_brief(job)}\n\n"
        f"WHY IT FITS\nStrengths: {', '.join(analysis.strengths) or 'n/a'}\n"
        f"Matched skills: {', '.join(analysis.matched_skills) or 'n/a'}"
    )


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------

REVIEWER_SYSTEM = (
    "You are the Reviewer, the final automated quality gate before a human "
    "approves submission. Critically assess the tailored resume, cover letter and "
    "the filled application form for a given job. Check: relevance to the role, "
    "absence of fabrication, that required form fields are answered, tone, and "
    "obvious red flags. Return a verdict (approve / revise / reject), a 0–100 "
    "quality score, a checklist, specific issues, and actionable suggestions. "
    "You advise; a human makes the final call."
)


def build_reviewer_user(
    job: Job,
    analysis: JobAnalysis,
    resume: TailoredResume,
    cover_letter: CoverLetter,
    form_summary: str,
) -> str:
    return (
        f"JOB\nTitle: {job.title} @ {job.company}\n"
        f"Match score: {analysis.match_score}\n\n"
        f"TAILORED RESUME\n{resume.markdown}\n\n"
        f"COVER LETTER\n{cover_letter.text}\n\n"
        f"FILLED FORM\n{form_summary}"
    )


# ---------------------------------------------------------------------------
# Summarizer
# ---------------------------------------------------------------------------

SUMMARIZER_SYSTEM = (
    "You are the Summarizer. Write a short, friendly plain-text briefing (max ~150 "
    "words) for the candidate describing what the agent did in this run: the job "
    "found, the match, what was drafted, the current status, and clear next steps. "
    "Do not use markdown headings; a few short paragraphs or bullet lines are fine."
)


def build_summarizer_user(context: str) -> str:
    return f"RUN CONTEXT\n{context}\n\nWrite the briefing."
