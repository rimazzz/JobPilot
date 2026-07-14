"""The multi-agent nodes that make up the JobPilot workflow."""

from __future__ import annotations

from jobpilot.agents.application import ApplicationAgent
from jobpilot.agents.base import BaseAgent
from jobpilot.agents.cover_letter import CoverLetterAgent
from jobpilot.agents.job_analyzer import JobAnalyzerAgent
from jobpilot.agents.planner import PlannerAgent
from jobpilot.agents.resume import ResumeAgent, render_resume_markdown
from jobpilot.agents.reviewer import ReviewerAgent, summarise_form
from jobpilot.agents.search import SearchAgent
from jobpilot.agents.summarizer import SummarizerAgent

__all__ = [
    "BaseAgent",
    "PlannerAgent",
    "SearchAgent",
    "JobAnalyzerAgent",
    "ResumeAgent",
    "CoverLetterAgent",
    "ApplicationAgent",
    "ReviewerAgent",
    "SummarizerAgent",
    "render_resume_markdown",
    "summarise_form",
]
