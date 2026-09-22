"""Transport attempts, proved at the HTTP layer (amendment P.8.1).

The config-level assertion shows the knobs are passed. It cannot show how many
requests actually leave the process, and on host 3 that number was ten. These
run the real `get_model` path against a local stub and count inbound requests.

The stub returns **500**: most clients do not retry a 400 at all, so one
request under a 400 would prove nothing, and 429's `Retry-After` would add
waiting of its own.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "_transport_probe.py"


def probe(attempts: int, when: str = "before") -> dict:
    """Subprocess, so LiteLLM's global state cannot leak between cases.

    A clean environment is passed explicitly: the control sets the retry
    variable inside the child, and it must not reach this process or any other
    test.
    """
    import os
    env = {k: v for k, v in os.environ.items()
           if k != "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"}
    r = subprocess.run([sys.executable, str(PROBE), str(attempts), when],
                       cwd=ROOT, capture_output=True, text=True, timeout=600,
                       env=env)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT" not in os.environ, \
        "the probe leaked its variable into the test process"
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def registered():
    return probe(int(P.RETRY_ENV["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"]))


@pytest.fixture(scope="module")
def control():
    """Two attempts allowed, to show the probe can see a retry when one
    happens. Test-only: it never enters the pilot configuration."""
    return probe(2)


# ── the registered policy ──
def test_one_logical_request_enters_the_transport_once(registered):
    assert registered["requested_attempts"] == 1
    assert registered["http_requests"] == 1


def test_there_is_no_backoff(registered):
    assert registered["gaps_between_requests"] == []
    assert registered["elapsed_seconds"] < 3.0, \
        "a tenacity backoff starts at 4 s; anything near that is a retry"


def test_the_failure_stays_an_infrastructure_error(registered):
    assert registered["exception"] == "InternalServerError"


def test_the_address_used_is_the_registered_one(registered):
    assert registered["model_name"] == "openai/Qwen/Qwen3.6-27B-FP8"
    assert registered["num_retries"] == 0 and registered["max_retries"] == 0


def test_a_transport_failure_never_becomes_a_verdict():
    """The same failure, through run_cell: BACKEND_ERROR, no verdict."""
    from agentseism import real_backend as RB
    r = RB._error_result(
        {"task": "t", "step_limit": 250, "hint": "full"},
        P.HINT_SHA256["full"], "img@sha256:" + "a" * 64,
        RB.BackendConfig(image_digests={}, work_dir=Path("."),
                         model_base_url="http://127.0.0.1:1/v1",
                         model_name="Qwen/Qwen3.6-27B-FP8",
                         model_revision="x"),
        0.0, "InternalServerError: stub", None)
    assert r["outcome_state"] == RB.BACKEND_ERROR
    assert r["evaluator_resolved"] is None
    assert r["outcome_state"] != RB.RESOLVED_FALSE
    assert r["enters_pilot_outcome"] is False


# ── the control: the probe can see a retry ──
def test_the_probe_observes_a_retry_when_one_is_allowed(control):
    """Without this, 'one request' might only mean the probe cannot count."""
    assert control["requested_attempts"] == 2
    assert control["http_requests"] == 2


def test_the_control_shows_the_backoff_the_registered_run_lacks(control):
    assert control["gaps_between_requests"], "no gap recorded"
    assert control["gaps_between_requests"][0] >= 3.5
    assert control["elapsed_seconds"] >= 4.0


def test_the_two_runs_differ_only_in_the_registered_variable(registered, control):
    assert control["http_requests"] > registered["http_requests"]
    assert control["model_name"] == registered["model_name"]
    assert control["num_retries"] == registered["num_retries"] == 0


# ── the variable the policy depends on ──
def test_the_retry_layer_still_reads_the_variable_we_set():
    """Setting an environment variable nothing reads looks exactly like
    setting one that works, so the installed source is asserted."""
    import inspect

    from minisweagent.models.utils import retry
    src = inspect.getsource(retry)
    assert "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT" in src, \
        "the retry layer no longer reads this variable; re-register the policy"
    assert "stop_after_attempt" in src
    assert "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT" in P.RETRY_ENV


def test_the_default_is_the_ten_attempts_host_3_saw():
    import inspect

    from minisweagent.models.utils import retry
    assert '"10"' in inspect.getsource(retry), \
        "the default changed; the host-3 observation no longer explains itself"


def test_the_env_in_force_is_returned_for_the_record(monkeypatch):
    from agentseism.real_backend import assert_retry_env
    monkeypatch.setenv("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", "1")
    assert assert_retry_env() == P.RETRY_ENV


def test_the_env_policy_is_inside_the_protocol_hash():
    before = P.protocol_hash()
    P.RETRY_ENV["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = "10"
    try:
        assert P.protocol_hash() != before
    finally:
        P.RETRY_ENV["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = "1"
    assert P.protocol_hash() == before


# ── when the variable is read (P.8.1 review) ──
def test_the_variable_set_before_import_gives_one_request():
    r = probe(1, "before")
    assert r["env_set"] == "before"
    assert r["http_requests"] == 1
    assert r["gaps_between_requests"] == []


def test_the_variable_is_read_at_call_time_on_this_version():
    """Measured, not assumed. If a later version moves the `os.getenv` to
    import or decoration time this fails, and the export-before-Python rule
    stops being belt-and-braces and becomes the only thing holding."""
    r = probe(1, "after")
    assert r["env_set"] == "after"
    assert r["http_requests"] == 1, (
        "setting the variable after import no longer takes effect on this "
        "version; the shell export is now load-bearing and the backend must "
        "still refuse to repair it")


def test_a_late_value_is_still_not_accepted_by_the_backend(monkeypatch):
    """Even though it would work, the backend refuses to run without the
    variable already in force: a process that repairs its own transport policy
    cannot report whether the policy held when it started."""
    from agentseism.real_backend import BackendUnavailable, assert_retry_env
    monkeypatch.delenv("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", raising=False)
    with pytest.raises(BackendUnavailable) as e:
        assert_retry_env()
    assert "exported before Python starts" in str(e.value)
    assert "does not repair it" in str(e.value)


def test_a_wrong_value_in_the_environment_is_refused(monkeypatch):
    from agentseism.real_backend import BackendUnavailable, assert_retry_env
    monkeypatch.setenv("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", "10")
    with pytest.raises(BackendUnavailable):
        assert_retry_env()


def test_the_backend_never_assigns_the_variable():
    """Structural: no code path may write it."""
    import inspect

    from agentseism import real_backend as RB
    src = inspect.getsource(RB)
    for bad in ('os.environ["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] =',
                "os.environ.setdefault(\"MSWEA_MODEL_RETRY",
                "environ[k] = v"):
        assert bad not in src, f"the backend sets the retry variable: {bad}"


def test_the_shell_exports_it_before_any_python():
    """All three entry points -- constructibility, smoke, pilot -- are started
    by this script and inherit its environment."""
    script = (ROOT / "inference/stage_b_preflight.sh").read_text()
    lines = script.splitlines()
    export_at = next(i for i, l in enumerate(lines)
                     if l.startswith("export MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1"))
    first_python = next(i for i, l in enumerate(lines)
                        if "venv-eval/bin/python" in l or "python3 -" in l)
    assert export_at < first_python, "a Python starts before the export"
