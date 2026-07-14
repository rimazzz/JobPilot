"""Tests for the command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from jobpilot import cli

SAMPLE_CANDIDATE = Path(__file__).resolve().parent.parent / "data" / "sample_candidate.json"


def test_version_command(capsys):
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip()


def test_load_candidate_parses_sample():
    candidate = cli._load_candidate(str(SAMPLE_CANDIDATE))
    assert candidate.full_name == "Jordan Rivera"
    assert candidate.skills


def test_load_candidate_missing_file():
    with pytest.raises(SystemExit):
        cli._load_candidate("does-not-exist.json")


def test_decide_flags():
    assert cli._decide(argparse.Namespace(approve=True, reject=False)) is True
    assert cli._decide(argparse.Namespace(approve=False, reject=True)) is False


def test_approve_and_reject_mutually_exclusive():
    with pytest.raises(SystemExit):
        cli.main(
            ["run", "--candidate", str(SAMPLE_CANDIDATE), "--goal", "x", "--approve", "--reject"]
        )


def test_run_reject_end_to_end(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("JOBPILOT_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("JOBPILOT_BROWSER_MODE", "simulated")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    code = cli.main(
        [
            "run",
            "--candidate",
            str(SAMPLE_CANDIDATE),
            "--goal",
            "Senior Python engineer",
            "--reject",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "TAILORED RESUME" in out
    assert "Final status: rejected" in out
