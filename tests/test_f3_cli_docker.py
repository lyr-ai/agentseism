"""F3's three cells, through the public CLI, in local Docker.

The precondition on renting anything: F3 is registered but not runnable until
its own three cells pass through `pilot.main()` against real containers and the
real SWE-bench evaluator, exactly as the pilot's repair was verified.

Opt-in — set `AGENTSEISM_DOCKER_TESTS=1`. Always collected so the preflight's
frozen test count stays stable, and skipped otherwise.

The pilot equivalent of this test (`test_real_cli_docker.py`) asserts the runner
*stops* after one block, because the pilot had 18 cells and only one was
authorised. F3 asserts the opposite ending: three cells **are** the experiment,
so the correct outcome is completion, not a budget stop. That difference is the
design's, not the runner's -- both go through the same `run_pilot`.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _docker_guard import run_probe
from agentseism import f3_protocol as F, pilot_protocol as P

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "_cli_cell_probe.py"

requires_docker = pytest.mark.skipif(
    not os.environ.get("AGENTSEISM_DOCKER_TESTS") or not shutil.which("docker"),
    reason="set AGENTSEISM_DOCKER_TESTS=1 and have Docker to run this")

CLOSED_PILOT_PROTOCOL_HASH = "b7af66ca3ab783ab"
CLOSED_PILOT_ORDER_HASH = "cfe8856c9c9167b5"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    work = tmp_path_factory.mktemp("f3-cli")
    return run_probe([sys.executable, str(PROBE), str(work), "f3"], cwd=ROOT)


@requires_docker
def test_the_public_cli_executes_all_three_f3_cells(run):
    assert run["exception"] is None
    assert run["experiment"] == "f3"
    assert run["registered_cells"] == 3
    assert len(run["artifacts"]) == 3


@requires_docker
def test_f3_completes_rather_than_stopping_at_a_block_boundary(run):
    """Three cells are the whole design, so there is no next block to withhold.

    This is why the registration does not claim `$12 absolute` can interrupt a
    running cell: nothing re-reads billing between cell 1 and cell 3.
    """
    assert run["stopped"] is None
    assert run["rc"] == 0
    assert run["report"]["state"] == "complete_3"
    assert run["report"]["cells_registered"] == 3
    assert run["report"]["verdict_allowed"] is False


@requires_docker
def test_every_f3_artifact_verifies_and_is_real(run):
    assert all(a["digest_ok"] for a in run["artifacts"])
    assert {a["synthetic"] for a in run["artifacts"]} == {False}


@requires_docker
def test_no_f3_artifact_carries_the_closed_pilots_identity(run):
    """The negative assertion, on real evidence rather than a synthetic run."""
    for a in run["artifacts"]:
        assert a["protocol_hash"] == F.SPEC.protocol_hash
        assert a["order_hash"] == F.ORDER_HASH
        assert a["protocol_hash"] != CLOSED_PILOT_PROTOCOL_HASH
        assert a["order_hash"] != CLOSED_PILOT_ORDER_HASH


@requires_docker
def test_each_arm_appears_exactly_once(run):
    names = [a["file"] for a in run["artifacts"]]
    assert len(names) == 3
    for arm in ("baseline", "M1", "M2"):
        assert sum(arm in n for n in names) == 1, (arm, names)
    assert all(F.TASK in n and "_r0.json" in n for n in names)


@requires_docker
def test_every_f3_cell_produces_a_scorable_termination_and_a_verdict(run):
    """F3's registered pass condition.

    `RESOLVED_FALSE` counts. F3 asks whether the path produces a verdict, not
    which verdict -- reading a false resolution as failure would be reading an
    agent outcome as an infrastructure outcome.
    """
    for a in run["artifacts"]:
        assert a["termination"] in P.SCORABLE, a
        assert a["outcome_state"] in ("RESOLVED_TRUE", "RESOLVED_FALSE"), a
        assert isinstance(a["evaluator_resolved"], bool), a


@requires_docker
def test_the_registered_policies_hold_in_every_f3_cell(run):
    for a in run["artifacts"]:
        assert a["transport_attempts"] == 1
        assert a["challenge_injections"] == 1
