"""One registered block, driven through the public CLI (`pilot.main`).

Host 5 stopped because `agentseism.pilot --backend real` could not invoke the
backend, and nothing had ever executed that entry point: the smoke test calls
`run_cell` directly. This is the test that would have caught it.

Opt-in — it starts real containers and runs the real SWE-bench harness. Set
`AGENTSEISM_DOCKER_TESTS=1`. Always collected, so the preflight's frozen count
stays stable, and skipped otherwise.

Scope is **one block, three cells**, because a block is the smallest unit the
budget authorises. `tests/_cli_cell_probe.py` is a helper that arranges the
fixture and calls `pilot.main()`; it is not a second execution path.
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
from agentseism import pilot, pilot_protocol as P

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "_cli_cell_probe.py"

requires_docker = pytest.mark.skipif(
    not os.environ.get("AGENTSEISM_DOCKER_TESTS") or not shutil.which("docker"),
    reason="set AGENTSEISM_DOCKER_TESTS=1 and have Docker to run this")

EXPECTED_CELLS_IN_BLOCK = 3


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    work = tmp_path_factory.mktemp("cli-block")
    return run_probe([sys.executable, str(PROBE), str(work)], cwd=ROOT)


# ── the entry point runs, and runs exactly the authorised block ──
@requires_docker
def test_the_public_cli_executes_the_authorised_block(run):
    assert run["exception"] is None
    assert run["registered_cells"] == P.CELLS == 18
    assert run["cells_in_block_0"] == EXPECTED_CELLS_IN_BLOCK
    assert len(run["artifacts"]) == EXPECTED_CELLS_IN_BLOCK


@requires_docker
def test_it_does_not_run_one_cell_more(run):
    """One reading authorises one block. The runner must not drift into the
    next one, and the count is frozen so a plan change cannot enlarge this
    test silently."""
    assert len(run["artifacts"]) == EXPECTED_CELLS_IN_BLOCK
    names = [a["file"] for a in run["artifacts"]]
    assert sorted(names) == names
    assert all("_r0.json" in n for n in names)


@requires_docker
def test_it_stops_before_the_next_block_rather_than_failing(run):
    """`stale_reading` is the success condition, not a failure: it is the
    runner declining to start work nobody authorised."""
    assert run["stopped"] is not None
    assert run["stopped"]["stop_kind"] == "stale_reading"
    assert "already authorised a block" in run["stopped"]["detail"]
    assert run["rc"] == 1, "a budget stop exits non-zero by design"


# ── the artifacts are real, complete and verifiable ──
@requires_docker
def test_every_artifact_verifies_against_its_digest(run):
    assert all(a["digest_ok"] for a in run["artifacts"])


@requires_docker
def test_no_artifact_is_synthetic(run):
    assert {a["synthetic"] for a in run["artifacts"]} == {False}


@requires_docker
def test_every_cell_carries_an_explicit_evaluator_boolean(run):
    for a in run["artifacts"]:
        assert isinstance(a["evaluator_resolved"], bool), a
        assert a["outcome_state"] in ("RESOLVED_TRUE", "RESOLVED_FALSE")
        assert a["enters_pilot_outcome"] is True
        assert a["termination"] in P.SCORABLE


@requires_docker
def test_the_registered_policies_are_in_every_cell(run):
    for a in run["artifacts"]:
        assert a["transport_attempts"] == 1
        assert a["challenge_injections"] == 1


# ── the live-session binding, on this platform ──
def _fake_vllm(model=P.HINTS and "Qwen/Qwen3.6-27B-FP8",
               revision="e89b16ebf1988b3d6befa7de50abc2d76f26eb09"):
    return subprocess.Popen(
        ["/bin/sh", "-c", "while :; do sleep 1; done",
         "vllm.entrypoints.openai.api_server", "--model", model,
         "--revision", revision])


def test_a_live_matching_process_is_accepted():
    import time
    p = _fake_vllm()
    time.sleep(1)
    try:
        pilot._live_serving_session({
            "vllm_pid": str(p.pid), "model": "Qwen/Qwen3.6-27B-FP8",
            "model_revision": "e89b16ebf1988b3d6befa7de50abc2d76f26eb09"})
    finally:
        p.kill()


def test_a_live_process_with_the_wrong_model_is_refused():
    import time
    p = _fake_vllm()
    time.sleep(1)
    try:
        with pytest.raises(pilot.PilotStop) as e:
            pilot._live_serving_session({
                "vllm_pid": str(p.pid), "model": "some-other-model",
                "model_revision": "e89b16ebf1988b3d6befa7de50abc2d76f26eb09"})
        assert "does not match the fingerprint" in str(e.value)
    finally:
        p.kill()


def test_a_live_process_with_the_wrong_revision_is_refused():
    import time
    p = _fake_vllm()
    time.sleep(1)
    try:
        with pytest.raises(pilot.PilotStop):
            pilot._live_serving_session({
                "vllm_pid": str(p.pid), "model": "Qwen/Qwen3.6-27B-FP8",
                "model_revision": "0000000000000000000000000000000000000000"})
    finally:
        p.kill()


def test_a_dead_pid_is_refused():
    with pytest.raises(pilot.PilotStop) as e:
        pilot._live_serving_session({"vllm_pid": "999999", "model": "m",
                                     "model_revision": "r"})
    assert "not alive" in str(e.value)


def test_the_binding_is_pid_and_command_line_not_start_time():
    """Stated because it would be easy to claim more.

    `_live_serving_session` compares the pid's **command line** against the
    fingerprint's model and revision. It does **not** compare a start time:
    the fingerprint records `vllm_started_at`, which is when the server became
    ready, and the process's own start time is a different quantity in a
    different format. A pid reused by a process with a matching command line
    would pass this check. The preflight script does compare pid plus start
    time, in `vllm_identity`, but that value is not carried in the report the
    CLI reads.
    """
    import inspect
    src = inspect.getsource(pilot._live_serving_session)
    assert "vllm_started_at" not in src
    assert "model_revision" in src
