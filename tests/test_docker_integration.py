"""The chain against a real container and the real evaluator.

Only one thing in the pilot genuinely needs a GPU: whether the pinned Qwen
model, through vLLM's parser, emits a usable tool call. Everything else runs
on CPU and Docker, and runs here, so that a paid smoke attempt carries exactly
one unknown.

Opt-in: these pull a 1 GB image and start containers. Set
`AGENTSEISM_DOCKER_TESTS=1`. They are always *collected*, so the preflight's
frozen test count stays stable, and they are skipped unless asked for --
preflight must not perform an unregistered execution.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P
from agentseism import real_backend as RB

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "_docker_integration_probe.py"

requires_docker = pytest.mark.skipif(
    not os.environ.get("AGENTSEISM_DOCKER_TESTS") or not shutil.which("docker"),
    reason="set AGENTSEISM_DOCKER_TESTS=1 and have Docker to run these")


def probe(mode: str, work: Path) -> dict:
    env = dict(os.environ, PROBE_WORK=str(work))
    r = subprocess.run([sys.executable, str(PROBE), mode], cwd=ROOT,
                       capture_output=True, text=True, timeout=1800, env=env)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    return probe("full", tmp_path_factory.mktemp("docker-full"))


@pytest.fixture(scope="module")
def timed_out(tmp_path_factory):
    return probe("timeout", tmp_path_factory.mktemp("docker-timeout"))


# 1-2. the exact image, a real container, a real /testbed
@requires_docker
def test_it_runs_the_exact_frozen_image(full):
    assert full["image_digest"].endswith(
        "@sha256:e38365e835d4ba57f3e7331778894f51ac20bf6c5893827065da8657525e123f")
    assert "@sha256:" in full["image_digest"]


@requires_docker
def test_the_agent_executed_inside_the_container(full):
    assert full["exception"] is None
    assert full["n_calls"] >= 3
    assert full["infrastructure_status"] == "OK"


# 3-4. stubbed model, first tool call, challenge, recovery
@requires_docker
def test_the_challenge_fires_once_against_a_real_container(full):
    assert full["challenge_status"] == "FIRED"
    assert full["challenge_injections"] == 1
    assert full["recovered"] is True


@requires_docker
def test_the_suppressed_action_never_touched_the_real_workspace(full):
    """Positive evidence: the suppressed command edits a tracked file, so it
    would appear in the patch if it had run."""
    assert full["patch_has_suppressed"] is False
    assert full["suppressed_actions"] == [
        "cd /testbed && printf '\\nSUPPRESSED_SHOULD_NOT_APPEAR\\n' >> CHANGELOG.rst"]


# 5. a real patch out of the real workspace
@requires_docker
def test_a_real_patch_is_extracted_from_the_workspace(full):
    assert full["patch_bytes"] > 0
    assert full["patch_has_recovery"] is True


# 6-7. the real evaluator, an explicit boolean
@requires_docker
def test_the_real_evaluator_ran_and_returned_an_explicit_boolean(full):
    assert isinstance(full["evaluator_resolved"], bool)
    assert full["evaluator_report_path"].endswith("report.json")
    assert Path(full["evaluator_report_path"]).exists()


@requires_docker
def test_a_definite_verdict_enters_the_pilot_outcome(full):
    assert full["outcome_state"] in (RB.RESOLVED_TRUE, RB.RESOLVED_FALSE)
    assert full["enters_pilot_outcome"] is True
    assert full["termination"] in P.SCORABLE


@requires_docker
def test_one_transport_attempt_through_the_whole_chain(full):
    assert full["transport_attempts"] == 1
    assert full["http_requests"] == full["n_calls"]


# 9. the cap, same code path, and the evaluator must not run
@requires_docker
def test_a_wall_clock_cap_censors_and_never_grades(timed_out):
    assert timed_out["infrastructure_status"] == RB.INFRA_TIMEOUT_1200S
    assert timed_out["outcome_state"] == RB.INFRA_TIMEOUT_1200S
    assert timed_out["enters_pilot_outcome"] is False
    assert timed_out["evaluator_resolved"] is None
    assert timed_out["evaluator_report_path"] == "", \
        "the evaluator ran on a censored run"
    assert timed_out["termination"] == P.INFRA_TIMEOUT_1200S


# the verdict reader, unit-level, against the real report shapes
def test_the_verdict_reader_uses_the_projects_existing_checker():
    body = {"patch_exists": True, "patch_successfully_applied": True,
            "infra_failure": False, "resolved": False,
            "tests_status": {}}
    task = "pytest-dev__pytest-10051"
    assert RB._verdict({task: {**body, "resolved": True}}, task) is True
    assert RB._verdict({task: body}, task) is False
    assert RB._verdict({task: {**body, "infra_failure": True}}, task) is None
    assert RB._verdict({task: {**body, "patch_exists": False}}, task) is None
    assert RB._verdict({task: {**body, "patch_successfully_applied": False}},
                       task) is None
    assert RB._verdict({}, task) is None


def test_the_run_level_summary_is_not_the_verdict():
    """A real run graded this task `resolved: False` with 15 PASS_TO_PASS
    successes while the run-level summary filed it under
    `ambiguous_failure_ids / no_tests_collected`. The per-instance report is
    authoritative; reading the summary produced EVALUATOR_UNDECIDED."""
    summary = {"completed_ids": ["t"], "resolved_ids": [],
               "unresolved_ids": ["t"], "ambiguous_failure_ids": ["t"],
               "failure_reasons": {"t": "no_tests_collected"}}
    assert RB._verdict(summary, "t") is None
