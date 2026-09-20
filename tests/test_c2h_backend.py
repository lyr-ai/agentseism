"""The real C2-H backend, under mocks. No network, no model, no Docker.

Each test asserts a boundary the backend must hold before any machine is
rented: that construction is inert, that one serving process serves the whole
experiment, that nothing retries invisibly, that a failure stops rather than
skips, and that a continuation uses the frozen manifest verbatim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

from experiments.coding import c2h_protocol as P
from experiments.coding.c2h_backend import (
    IntegrityStop, RealBackend, UnlabelledDonor,
)

HEAVY = ("litellm", "vllm", "docker", "minisweagent", "httpx", "torch")


def be(tmp_path, **kw):
    return RealBackend(out=tmp_path, endpoint="http://127.0.0.1:8000/v1",
                       image="img:latest", **kw)


# ── 1. construction and import are inert ──
def test_construction_touches_no_network_model_or_docker(tmp_path):
    before = {m for m in sys.modules if any(h in m for h in HEAVY)}
    b = be(tmp_path)
    after = {m for m in sys.modules if any(h in m for h in HEAVY)}
    assert after == before
    assert b._model is None


def test_construction_creates_no_files(tmp_path):
    be(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_resolve_only_is_side_effect_free_with_a_real_backend(tmp_path, capsys):
    from experiments.coding.run_c2h import main
    out = tmp_path / "o"
    with mock.patch("experiments.coding.c2h_backend.RealBackend") as R:
        rc = main(["--resolve-only", "--backend", "real", "--image", "i",
                   "--out", str(out)])
    assert rc == 0
    R.assert_not_called()                      # never even constructed
    assert not (out / "run.jsonl").exists()


# ── 2. one serving process for the whole experiment ──
def test_client_is_built_once_and_shared(tmp_path):
    b = be(tmp_path)
    sentinel = object()
    with mock.patch("agents.coding.instrumented_model.InstrumentedLitellmModel",
                    return_value=sentinel) as M, \
         mock.patch.object(RealBackend, "identity", return_value={"vllm_pid": "1"}):
        assert b.model() is sentinel
        assert b.model() is sentinel
    assert M.call_count == 1


def test_the_registered_transport_policy_is_used_verbatim(tmp_path):
    b = be(tmp_path)
    with mock.patch("agents.coding.instrumented_model.InstrumentedLitellmModel") as M, \
         mock.patch.object(RealBackend, "identity", return_value={}):
        b.model()
    kw = M.call_args.kwargs
    assert kw["stream"] is True
    assert kw["attempt_timeout"] == 180
    assert kw["max_attempts"] == 6
    assert kw["model_name"] == f"openai/{P.MODEL['id']}"


def test_no_retry_wrapper_is_layered_on_the_client(tmp_path):
    """The client already counts its attempts. A second layer would hide them."""
    src = Path("experiments/coding/c2h_backend.py").read_text()
    body = src.split("class RealBackend")[1]
    for banned in ("for attempt in", "while True", "tenacity", "@retry",
                   "max_retries=", "time.sleep"):
        assert banned not in body, f"{banned!r} suggests a second retry layer"


@pytest.mark.parametrize("field", ["endpoint", "vllm_pid", "gpu", "hostname",
                                   "model_id", "revision"])
def test_a_changed_serving_process_is_an_integrity_stop(tmp_path, field):
    b = be(tmp_path)
    b._identity = {"endpoint": "e", "vllm_pid": "1", "gpu": "g",
                   "hostname": "h", "model_id": "m", "revision": "r"}
    drifted = dict(b._identity) | {field: "changed"}
    with mock.patch.object(RealBackend, "identity", return_value=drifted):
        with pytest.raises(IntegrityStop) as e:
            b.assert_same_serving_process()
    assert e.value.stage == "serving_identity"


def test_identity_is_recorded_on_every_record(tmp_path):
    b = be(tmp_path, checker=lambda r: "PASS")
    ident = {"endpoint": "e", "vllm_pid": "7", "gpu": "g", "hostname": "h",
             "model_id": "m", "revision": "r"}
    with mock.patch.object(RealBackend, "identity", return_value=ident), \
         mock.patch.object(RealBackend, "_execute",
                           return_value={"exit_status": "Submitted", "raw": "x"}):
        b.run_donor(0, "d0")
    rec = json.loads((tmp_path / "raw" / "donor_00.json").read_text())
    assert rec["identity"] == ident


# ── 3. the record keeps everything, not just the parse ──
def test_the_artifact_keeps_the_whole_turn(tmp_path):
    full = {"exit_status": "Submitted", "messages": [{"role": "assistant"}],
            "raw_responses": ["..."], "tool_calls": [{"command": "ls"}],
            "transport_events": [{"attempt": 1, "outcome": "ok"}],
            "errors": []}
    b = be(tmp_path, checker=lambda r: "FAIL")
    with mock.patch.object(RealBackend, "identity", return_value={}), \
         mock.patch.object(RealBackend, "_execute", return_value=full):
        b.run_donor(3, "d3")
    rec = json.loads((tmp_path / "raw" / "donor_03.json").read_text())
    for key in full:
        assert key in rec, f"{key} was dropped from the artifact"
    assert rec["started"] and rec["finished"] and rec["acquisition_index"] == 3


# ── 4. labelling is frozen, never manual ──
def test_an_unlabelled_donor_is_invalid_and_counted_in_neither_arm(tmp_path):
    def checker(_):
        raise UnlabelledDonor("checker could not decide")
    b = be(tmp_path, checker=checker)
    with mock.patch.object(RealBackend, "identity", return_value={}), \
         mock.patch.object(RealBackend, "_execute", return_value={"exit_status": "x"}):
        assert b.run_donor(1, "d1") == "invalid"
    rec = json.loads((tmp_path / "raw" / "donor_01.json").read_text())
    assert rec["label"] == "invalid" and rec["label_error"]


def test_a_checker_verdict_outside_the_two_arms_is_invalid(tmp_path):
    b = be(tmp_path, checker=lambda r: "MAYBE")
    with mock.patch.object(RealBackend, "identity", return_value={}), \
         mock.patch.object(RealBackend, "_execute", return_value={"exit_status": "x"}):
        assert b.run_donor(2, "d2") == "invalid"


def test_no_manual_labelling_entry_point_exists(tmp_path):
    b = be(tmp_path)
    for name in dir(b):
        assert "manual" not in name.lower()
        assert "override" not in name.lower()


# ── 5. continuations use the manifest verbatim ──
def test_continuation_uses_the_spec_and_never_reselects_a_donor(tmp_path):
    spec = {"run_id": "c2h__FAIL__d0__h24__k1", "arm": "FAIL", "donor_id": "d0",
            "donor_run_id": "donor_00", "horizon": 24, "replicate": 1,
            "step_limit": 226}
    seen = {}
    def fake_exec(self, run_id, prefix, step_limit, **extra):
        seen.update(run_id=run_id, prefix=prefix, step_limit=step_limit, **extra)
        return {"exit_status": "Submitted"}
    b = be(tmp_path)
    with mock.patch.object(RealBackend, "identity", return_value={}), \
         mock.patch.object(RealBackend, "_execute", fake_exec):
        out = b.run_continuation(spec)
    assert seen["prefix"] == "donor_00" and seen["horizon"] == 24
    assert seen["step_limit"] == 226
    assert out["run_id"] == spec["run_id"] and out["artifact_sha256"]


@pytest.mark.parametrize("missing", ["run_id", "donor_run_id", "horizon",
                                     "step_limit", "arm"])
def test_an_incomplete_spec_is_an_integrity_stop(tmp_path, missing):
    spec = {"run_id": "r", "donor_run_id": "d", "horizon": 16,
            "step_limit": 234, "arm": "FAIL"}
    del spec[missing]
    b = be(tmp_path)
    with mock.patch.object(RealBackend, "identity", return_value={}):
        with pytest.raises(IntegrityStop) as e:
            b.run_continuation(spec)
    assert e.value.stage == "spec"


# ── 6. failures stop, never skip ──
@pytest.mark.parametrize("exc", [RuntimeError("docker: no such image"),
                                 TimeoutError("container timeout"),
                                 ValueError("could not parse response")])
def test_container_timeout_and_parse_failures_all_stop(tmp_path, exc):
    spec = {"run_id": "r", "arm": "FAIL", "donor_run_id": "d", "horizon": 16,
            "step_limit": 234}
    b = be(tmp_path)
    with mock.patch.object(RealBackend, "identity", return_value={}), \
         mock.patch.object(RealBackend, "_execute", side_effect=exc):
        with pytest.raises(IntegrityStop) as e:
            b.run_continuation(spec)
    assert e.value.stage == "continuation_execution"


def test_a_donor_failure_stops_rather_than_returning_a_label(tmp_path):
    b = be(tmp_path, checker=lambda r: "PASS")
    with mock.patch.object(RealBackend, "identity", return_value={}), \
         mock.patch.object(RealBackend, "_execute",
                           side_effect=RuntimeError("container died")):
        with pytest.raises(IntegrityStop) as e:
            b.run_donor(0, "d0")
    assert e.value.stage == "donor_execution"


def test_integrity_stop_propagates_unwrapped(tmp_path):
    b = be(tmp_path)
    inner = IntegrityStop("serving_identity", "drift")
    with mock.patch.object(RealBackend, "identity", return_value={}), \
         mock.patch.object(RealBackend, "_execute", side_effect=inner):
        with pytest.raises(IntegrityStop) as e:
            b.run_continuation({"run_id": "r", "arm": "F", "donor_run_id": "d",
                                "horizon": 16, "step_limit": 234})
    assert e.value is inner


# ── 7. artifacts and block completion ──
def test_block_is_complete_only_when_every_artifact_verifies(tmp_path):
    b = be(tmp_path)
    b._freeze("a", {"x": 1}); b._freeze("c", {"x": 3})
    assert b.block_complete(["a", "c"]) is True
    assert b.block_complete(["a", "b", "c"]) is False


def test_a_tampered_artifact_does_not_count(tmp_path):
    b = be(tmp_path)
    b._freeze("a", {"x": 1})
    (tmp_path / "raw" / "a.json").write_text('{"x": 999}')
    assert b.artifact_valid("a") is False
    assert b.block_complete(["a"]) is False


def test_execute_is_not_wired_and_says_so(tmp_path):
    b = be(tmp_path)
    with pytest.raises(IntegrityStop) as e:
        b._execute("r", prefix=None, step_limit=None)
    assert e.value.stage == "not_wired"


# ── 8. the CLI gates ──
def test_real_backend_refuses_without_the_confirmation_flag():
    from experiments.coding.run_c2h import main
    with pytest.raises(SystemExit) as e:
        main(["--backend", "real", "--image", "i", "--out", "/tmp/nope"])
    assert "--execute-registered-c2h" in str(e.value)


def test_real_backend_requires_an_image():
    from experiments.coding.run_c2h import main
    with pytest.raises(SystemExit) as e:
        main(["--backend", "real", "--execute-registered-c2h", "--out", "/tmp/nope"])
    assert "--image" in str(e.value)


def test_the_default_backend_is_not_real():
    import argparse
    from experiments.coding import run_c2h
    src = Path(run_c2h.__file__).read_text()
    assert 'choices=("fake", "real"), default="fake"' in src
    del argparse
