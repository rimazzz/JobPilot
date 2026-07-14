"""Assembly of the LangGraph workflow.

The graph wires the eight agents into a single directed flow with two decision
points and one human-in-the-loop breakpoint:

    START -> plan -> search -.(no jobs).-> summarize -> END
                       |
                    (jobs)
                       v
        analyze -> resume -> cover_letter -> fill -> review
                                                       |
                                              [interrupt: approval]
                                                       v
                                                 approval_gate -.(approved).-> submit -> summarize
                                                       |                                     ^
                                                  (rejected) --------------------------------+

The graph is compiled with ``interrupt_before=["approval_gate"]`` and a
checkpointer, so a run pauses after review and resumes once a human decision is
written into the state.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from jobpilot.agents.application import ApplicationAgent, FillerFactory
from jobpilot.agents.cover_letter import CoverLetterAgent
from jobpilot.agents.job_analyzer import JobAnalyzerAgent
from jobpilot.agents.planner import PlannerAgent
from jobpilot.agents.resume import ResumeAgent
from jobpilot.agents.reviewer import ReviewerAgent
from jobpilot.agents.search import SearchAgent
from jobpilot.agents.summarizer import SummarizerAgent
from jobpilot.config import Settings, get_settings
from jobpilot.schemas.state import AgentState, log
from jobpilot.serialization import build_serde
from jobpilot.tools.job_search import JobSearchProvider

#: The node at which a run pauses for human approval.
APPROVAL_NODE = "approval_gate"


def route_after_search(state: AgentState) -> str:
    """Continue to analysis when jobs exist, otherwise summarise and stop."""
    return "analyze" if state.get("jobs") else "summarize"


def route_after_approval(state: AgentState) -> str:
    """Submit only when a human approved; otherwise go straight to the summary."""
    approval = state.get("approval")
    return "submit" if (approval is not None and approval.approved) else "summarize"


async def approval_gate(state: AgentState) -> dict:
    """No-op node that runs *after* the human decision has been injected."""
    approval = state.get("approval")
    decided = "approved" if (approval is not None and approval.approved) else "rejected"
    return {"logs": log("human", f"Approval decision received: {decided}.")}


def build_graph(
    settings: Settings | None = None,
    *,
    llm: BaseChatModel | None = None,
    search_provider: JobSearchProvider | None = None,
    filler_factory: FillerFactory | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build and compile the JobPilot workflow.

    All collaborators are injectable, which keeps the graph fully testable
    without an LLM, a browser, or network access.
    """
    settings = settings or get_settings()

    planner = PlannerAgent(settings, llm)
    search = SearchAgent(settings, provider=search_provider, llm=llm)
    analyzer = JobAnalyzerAgent(settings, llm)
    resume = ResumeAgent(settings, llm)
    cover_letter = CoverLetterAgent(settings, llm)
    application = ApplicationAgent(settings, filler_factory=filler_factory, llm=llm)
    reviewer = ReviewerAgent(settings, llm)
    summarizer = SummarizerAgent(settings, llm)

    builder: StateGraph = StateGraph(AgentState)

    builder.add_node("plan", planner.run)
    builder.add_node("search", search.run)
    builder.add_node("analyze", analyzer.run)
    builder.add_node("resume", resume.run)
    builder.add_node("cover_letter", cover_letter.run)
    builder.add_node("fill", application.fill)
    builder.add_node("review", reviewer.run)
    builder.add_node(APPROVAL_NODE, approval_gate)
    builder.add_node("submit", application.submit)
    builder.add_node("summarize", summarizer.run)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "search")
    builder.add_conditional_edges(
        "search", route_after_search, {"analyze": "analyze", "summarize": "summarize"}
    )
    builder.add_edge("analyze", "resume")
    builder.add_edge("resume", "cover_letter")
    builder.add_edge("cover_letter", "fill")
    builder.add_edge("fill", "review")
    builder.add_edge("review", APPROVAL_NODE)
    builder.add_conditional_edges(
        APPROVAL_NODE, route_after_approval, {"submit": "submit", "summarize": "summarize"}
    )
    builder.add_edge("submit", "summarize")
    builder.add_edge("summarize", END)

    return builder.compile(
        checkpointer=checkpointer or MemorySaver(serde=build_serde()),
        interrupt_before=[APPROVAL_NODE],
    )
