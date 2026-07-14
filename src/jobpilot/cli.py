"""Command-line interface for JobPilot.

Examples::

    jobpilot run --candidate data/sample_candidate.json --goal "Senior Python, remote"
    jobpilot run --candidate cv.json --goal "ML engineer" --approve
    jobpilot serve --port 8000
    jobpilot version
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from pathlib import Path

from jobpilot import __version__
from jobpilot.logging_config import configure_logging
from jobpilot.orchestrator import Orchestrator, RunSnapshot
from jobpilot.schemas.application import ApprovalDecision
from jobpilot.schemas.candidate import CandidateProfile


def _ensure_utf8_output() -> None:
    """Make stdout/stderr emit UTF-8 so documents render on any platform."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            # pragma: no cover - stream may not be reconfigurable
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8")


def _load_candidate(path: str) -> CandidateProfile:
    file = Path(path)
    if not file.exists():
        raise SystemExit(f"Candidate file not found: {path}")
    try:
        return CandidateProfile.model_validate_json(file.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        raise SystemExit(f"Could not parse candidate file {path}: {exc}") from exc


def _hr(title: str) -> None:
    print(f"\n{'=' * 4} {title} {'=' * max(4, 60 - len(title))}")


def _print_run(snapshot: RunSnapshot) -> None:
    v = snapshot.values
    job = v.get("selected_job")
    analysis = v.get("analysis")
    resume = v.get("resume")
    cover = v.get("cover_letter")
    application = v.get("application")
    review = v.get("review")

    _hr("PLAN")
    plan = v.get("plan")
    if plan:
        print(f"Objective: {plan.objective}")
        print(f"Target role: {plan.target_role}")

    _hr("JOB")
    if job:
        print(f"{job.title} @ {job.company} — {job.location or 'n/a'}")
        print(f"URL: {job.application_url}")
    else:
        print("No matching job found.")

    if analysis:
        _hr("ANALYSIS")
        print(f"Match score: {analysis.match_score:.0f}/100 ({analysis.recommendation.value})")
        print(f"Matched: {', '.join(analysis.matched_skills[:8]) or 'n/a'}")
        print(f"Missing: {', '.join(analysis.missing_skills[:8]) or 'n/a'}")
        print(f"Summary: {analysis.summary}")

    if resume:
        _hr("TAILORED RESUME")
        print(resume.markdown)

    if cover:
        _hr("COVER LETTER")
        print(cover.text)

    if application and application.form:
        _hr("APPLICATION FORM")
        print(f"URL: {application.form.url}  (status: {application.status.value})")
        for field in application.form.fields:
            mark = "x" if field.filled else " "
            value = (field.value or "").splitlines()[0][:60] if field.value else ""
            print(f"  [{mark}] {field.label or field.name}: {value}")
        if application.screenshot_path:
            print(f"Preview artifact: {application.screenshot_path}")

    if review:
        _hr("REVIEW")
        print(f"Verdict: {review.verdict.value}  (score {review.score:.0f}/100)")
        for item in review.checklist:
            print(f"  [{'PASS' if item.passed else 'FAIL'}] {item.name} — {item.comment}")
        for suggestion in review.suggestions:
            print(f"  → {suggestion}")


def _decide(args: argparse.Namespace) -> bool:
    if args.approve:
        return True
    if args.reject:
        return False
    if not sys.stdin.isatty():
        print("\nNo TTY and no --approve/--reject flag; defaulting to REJECT (safe).")
        return False
    answer = input("\nApprove and submit this application? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


async def _run_async(args: argparse.Namespace) -> int:
    candidate = _load_candidate(args.candidate)
    orchestrator = Orchestrator()

    snapshot = await orchestrator.start_run(candidate, args.goal)
    _print_run(snapshot)

    if not snapshot.awaiting_approval:
        _hr("SUMMARY")
        print(snapshot.values.get("summary") or "Run finished.")
        return 0

    approved = _decide(args)
    snapshot = await orchestrator.approve(snapshot.thread_id, ApprovalDecision(approved=approved))

    _hr("RESULT")
    application = snapshot.values.get("application")
    print(f"Final status: {snapshot.status.value}")
    if application and application.submitted:
        print(f"Submitted. Confirmation: {application.confirmation}")
    _hr("SUMMARY")
    print(snapshot.values.get("summary") or "Run finished.")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    configure_logging("INFO" if args.verbose else "WARNING", "console")
    return asyncio.run(_run_async(args))


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "jobpilot.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobpilot", description="AI job application agent.")
    parser.add_argument("--version", action="version", version=f"jobpilot {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run an application end-to-end from the CLI.")
    run_p.add_argument("--candidate", required=True, help="Path to a candidate profile JSON file.")
    run_p.add_argument("--goal", required=True, help="Free-text description of the target job.")
    run_p.add_argument("--approve", action="store_true", help="Auto-approve submission.")
    run_p.add_argument("--reject", action="store_true", help="Auto-reject submission.")
    run_p.add_argument("--verbose", action="store_true", help="Show info-level logs.")
    run_p.set_defaults(func=_cmd_run)

    serve_p = sub.add_parser("serve", help="Start the FastAPI server.")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.add_argument("--reload", action="store_true")
    serve_p.set_defaults(func=_cmd_serve)

    version_p = sub.add_parser("version", help="Print the version.")
    version_p.set_defaults(func=lambda _a: print(__version__) or 0)

    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "approve", False) and getattr(args, "reject", False):
        parser.error("--approve and --reject are mutually exclusive")
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
