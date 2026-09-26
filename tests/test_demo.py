"""`seism demo`: zero-cost, deterministic, and decided by the real engine.

The demo's agent is simulated. These tests make sure nothing else is: the
verdicts it prints must be the ones `decide()` returns, through the shipped
contract defaults, with no network and in well under a minute.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time

import pytest

import agentseism.demo as D
from agentseism import capability
from agentseism.cli import main
from agentseism.resolve import resolve_and_validate

EXPECTED = ["✓ PASS", "✗ REGRESSION", "? INSUFFICIENT EVIDENCE"]


def run_cli(*args) -> tuple[str, float]:
    t = time.time()
    p = subprocess.run([sys.executable, "-m", "agentseism.cli", "demo", *args],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout, time.time() - t


def test_the_command_runs_fast_and_shows_the_three_verdicts_in_order():
    out, seconds = run_cli()
    assert seconds < 60
    pos = [out.index(f"Verdict: {v}") for v in EXPECTED]
    assert pos == sorted(pos)


def test_it_says_it_is_a_demonstration_and_points_at_real_evidence():
    out, _ = run_cli()
    assert "simulated agent, the real decision engine" in out
    assert "not evidence" in out
    assert "analysis/ci_v1/stageC/RESULTS.md" in out


def test_the_output_is_identical_on_every_run():
    assert run_cli()[0] == run_cli()[0]


def test_every_printed_verdict_is_what_decide_returned(monkeypatch):
    """The demo must not print a verdict of its own. Spy on the real decide()
    and check each printed verdict came from it, in order."""
    seen = []
    real = D.decide

    def spy(*a, **k):
        v = real(*a, **k)
        seen.append(v["verdict"])
        return v
    monkeypatch.setattr(D, "decide", spy)
    lines: list[str] = []
    assert D.main(out=lines.append) == 0
    assert seen == ["PASS", "REGRESSION", "INSUFFICIENT_EVIDENCE"]
    printed = [ln for ln in lines if "Verdict:" in ln]
    assert [p.split("Verdict: ")[1] for p in printed] == EXPECTED


def test_the_collapse_is_caught_by_the_capability_gate_not_the_average():
    """Scenario 2 is there to show what the capability gate adds: the broad
    gate passes, the capability gate fires on the broken task."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as t:
        r = D.run_scenario(2, D.SCENARIOS[1], Path(t))
    assert r["broad"] == "PASS"
    assert [Path(x).stem for x in r["capability"]["fired"]] == ["checkout"]


def test_it_needs_no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the demo tried to open a socket")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert D.main(out=lambda *_: None) == 0


def test_it_uses_the_shipped_defaults_not_demo_tuned_rules():
    c, _, _ = resolve_and_validate(D.CONTRACT)
    f = c.features["task_success"]
    assert f["practical_threshold"] == 0.10
    assert f["capability_regression"] == capability.DEFAULTS


def test_the_report_flag_prints_the_real_pr_report():
    out, _ = run_cli("--report")
    assert out.count("## AgentSeism:") == 3
    assert "## AgentSeism: REGRESSION — do not merge without review" in out


def test_it_is_a_seism_subcommand(capsys):
    assert main(["demo"]) == 0
    assert "Verdict: ✓ PASS" in capsys.readouterr().out
