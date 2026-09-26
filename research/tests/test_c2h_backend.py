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
    return RealBackend(out=tmp_path, endpoint="http://127.0.0.1:8000/v1", **kw)


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
        rc = main(["--resolve-only", "--backend", "real", "--out", str(out)])
    assert rc == 0
    R.assert_not_called()                      # never even constructed
    assert not (out / "run.jsonl").exists()


# ── 2. one serving process for the whole experiment ──
def _compliant_client():
    c = mock.MagicMock()
    c.config.model_kwargs = {"num_retries": 0}
    return c


def test_client_is_built_once_and_shared(tmp_path):
    b = be(tmp_path)
    sentinel = _compliant_client()
    with mock.patch("agents.coding.instrumented_model.InstrumentedLitellmModel",
                    return_value=sentinel) as M, \
         mock.patch.object(RealBackend, "identity", return_value={"vllm_pid": "1"}):
        assert b.model() is sentinel
        assert b.model() is sentinel
    assert M.call_count == 1


def test_the_registered_transport_policy_is_used_verbatim(tmp_path):
    b = be(tmp_path)
    with mock.patch("agents.coding.instrumented_model.InstrumentedLitellmModel",
                    return_value=_compliant_client()) as M, \
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
        return {"exit_status": "Submitted", "transport_attempts": 1,
                "transport_events": [{"attempt": 1, "outcome": "ok"}]}
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





# ── 8. the CLI gates ──
def test_real_backend_refuses_without_the_confirmation_flag():
    from experiments.coding.run_c2h import main
    with pytest.raises(SystemExit) as e:
        main(["--backend", "real", "--out", "/tmp/nope"])
    assert "--execute-registered-c2h" in str(e.value)


def test_the_image_is_registered_and_not_a_cli_option(tmp_path):
    """Changing the task changes the experiment, not its price."""
    from experiments.coding import run_c2h
    src = Path(run_c2h.__file__).read_text()
    assert "--image" not in src
    b = be(tmp_path)
    assert b.image == P.IMAGE and b.task == P.TASK
    with pytest.raises(TypeError):
        RealBackend(out=tmp_path, endpoint="e", image="other:tag")


def test_the_default_backend_is_not_real():
    import argparse
    from experiments.coding import run_c2h
    src = Path(run_c2h.__file__).read_text()
    assert 'choices=("fake", "real"), default="fake"' in src
    del argparse


# ── 9. no hidden retries: behaviour, not grep ──
def test_one_logical_request_enters_the_transport_once(tmp_path):
    """The behavioural half of the claim. grep cannot see litellm's own retry;
    this drives a request and counts entries into the layer below."""
    from agents.coding.instrumented_model import InstrumentedLitellmModel
    calls = {"n": 0}

    def fake_query(self, messages, **kw):
        calls["n"] += 1
        return mock.MagicMock(choices=[mock.MagicMock(
            message=mock.MagicMock(content="ok", tool_calls=[]))])

    with mock.patch.object(InstrumentedLitellmModel, "__init__",
                           lambda self, **kw: None):
        m = InstrumentedLitellmModel()
    m._stream = False
    m._max_attempts, m._retry_backoff, m._attempt_timeout = 6, 0, 180
    m._timeout, m._events = None, []
    m.abort_exceptions = ()
    with mock.patch("minisweagent.models.litellm_model.LitellmModel._query", fake_query):
        m._query([{"role": "user", "content": "x"}])
    assert calls["n"] == 1, "one logical request entered the transport more than once"
    assert len(m._events) == 1 and m._events[0]["outcome"] == "ok"


def test_num_retries_must_be_zero_underneath(tmp_path):
    good = mock.MagicMock(); good.config.model_kwargs = {"num_retries": 0}
    RealBackend.assert_no_hidden_retries(good)          # no raise
    for bad_value in (1, 5, None, "2"):
        bad = mock.MagicMock(); bad.config.model_kwargs = {"num_retries": bad_value}
        with pytest.raises(IntegrityStop) as e:
            RealBackend.assert_no_hidden_retries(bad)
        assert e.value.stage == "transport_policy"


def test_the_guard_runs_when_the_client_is_built(tmp_path):
    b = be(tmp_path)
    bad = mock.MagicMock(); bad.config.model_kwargs = {"num_retries": 3}
    with mock.patch("agents.coding.instrumented_model.InstrumentedLitellmModel",
                    return_value=bad), \
         mock.patch.object(RealBackend, "identity", return_value={}):
        with pytest.raises(IntegrityStop) as e:
            b.model()
    assert e.value.stage == "transport_policy"


def test_a_record_without_an_attempt_count_is_an_integrity_stop(tmp_path):
    spec = {"run_id": "r", "arm": "FAIL", "donor_run_id": "d", "horizon": 16,
            "step_limit": 234}
    b = be(tmp_path)
    with mock.patch.object(RealBackend, "identity", return_value={}), \
         mock.patch.object(RealBackend, "_execute",
                           return_value={"exit_status": "Submitted"}):
        with pytest.raises(IntegrityStop) as e:
            b.run_continuation(spec)
    assert e.value.stage == "attempt_record"


def test_attempts_are_carried_into_the_artifact(tmp_path):
    spec = {"run_id": "r", "arm": "FAIL", "donor_run_id": "d", "horizon": 16,
            "step_limit": 234}
    b = be(tmp_path)
    result = {"exit_status": "Submitted", "transport_attempts": 3,
              "transport_events": [{"attempt": i} for i in (1, 2, 3)]}
    with mock.patch.object(RealBackend, "identity", return_value={}), \
         mock.patch.object(RealBackend, "_execute", return_value=result):
        b.run_continuation(spec)
    rec = json.loads((tmp_path / "raw" / "r.json").read_text())
    assert rec["transport_attempts"] == 3 and len(rec["transport_events"]) == 3


# ── 10. the frozen checker, verified offline against all twenty donors ──
def test_checker_reproduces_every_frozen_label():
    from experiments.coding.c2h_checker import verify_against_frozen_labels
    r = verify_against_frozen_labels()
    assert r["n"] == 20
    assert (r["frozen_fail"], r["frozen_pass"]) == (4, 16)
    assert r["mismatches"] == [] and r["unlabelled"] == []
    assert r["identical"] is True


@pytest.mark.parametrize("body,expect", [
    ({"resolved": True, "patch_exists": True, "patch_successfully_applied": True}, "PASS"),
    ({"resolved": False, "patch_exists": True, "patch_successfully_applied": True}, "FAIL"),
])
def test_checker_rule_is_resolved_only(body, expect):
    from experiments.coding.c2h_checker import INSTANCE, label_from_report
    assert label_from_report({INSTANCE: body}) == expect


@pytest.mark.parametrize("body", [
    {"infra_failure": True, "resolved": False, "patch_exists": True,
     "patch_successfully_applied": True},
    {"patch_exists": False, "resolved": False},
    {"patch_exists": True, "patch_successfully_applied": False, "resolved": False},
    {"patch_exists": True, "patch_successfully_applied": True},
])
def test_non_verdicts_refuse_rather_than_becoming_FAIL(body):
    """Infra noise must not be recorded in the arm the experiment is about."""
    from experiments.coding.c2h_checker import INSTANCE, label_from_report
    with pytest.raises(UnlabelledDonor):
        label_from_report({INSTANCE: body})


# ── 11. no Docker anywhere in the test suite ──
@pytest.fixture(autouse=True)
def _no_docker(monkeypatch):
    """Any real Docker invocation fails the test that caused it."""
    import subprocess
    real = subprocess.run

    def guard(cmd, *a, **kw):
        argv = cmd if isinstance(cmd, (list, tuple)) else [str(cmd)]
        if any("docker" in str(x) for x in argv):
            raise AssertionError(f"a test invoked Docker: {argv}")
        return real(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", guard)


def test_the_docker_guard_actually_fires(tmp_path):
    """The guard raises; image_digest wraps it, so the evidence is the wrapped
    message. Either way no Docker ran, which is the point."""
    b = be(tmp_path)
    with pytest.raises(IntegrityStop) as e:
        b.image_digest()
    assert e.value.stage == "image_digest"
    assert "invoked Docker" in e.value.detail


# ── 12. the wired _execute: one path, differing only by prefix ──
class _Env:
    container_id = "container-abc123"
    def cleanup(self): pass


def _preflighted(tmp_path, **kw):
    """A backend as it exists after preflight(): identity resolved."""
    b = be(tmp_path, **kw)
    b._identity = {"endpoint": "e", "image_digest": "sha256:1"}
    b._lock_sha256 = "abc123"
    return b


def _wire(monkeypatch, tmp_path, prefix_seen, messages=None):
    """Patch materialize / ForkedAgent / yaml so _execute runs with no Docker."""
    import agents.coding.fork as fork_mod
    env = _Env()
    monkeypatch.setattr(fork_mod, "materialize",
                        lambda *a, **kw: (env, {"tracked_diff_hash": "T",
                                                "workspace_diff_hash": "W"}))

    class FakeAgent:
        def __init__(self, model, env, prefix_messages=None, **cfg):
            prefix_seen.append(list(prefix_messages or []))
            self.messages = messages if messages is not None else [
                {"role": "assistant",
                 "extra": {"actions": [{"command": "pytest -q"}],
                           "transport_attempts": 1,
                           "transport_events": [{"attempt": 1, "outcome": "ok"}]}}]
        def run(self, task):
            return {"exit_status": "Submitted", "submission": "diff --git"}

    import agents.coding.archiving_agent as arch
    monkeypatch.setattr("agents.coding.fork.forking", lambda base: FakeAgent)
    monkeypatch.setattr(arch, "archiving", lambda base: base)
    del arch


def test_donor_injects_no_prefix_and_continuation_does(tmp_path, monkeypatch):
    seen = []
    b = _preflighted(tmp_path)
    monkeypatch.setattr(RealBackend, "image_digest", lambda self: "sha256:dead")
    monkeypatch.setattr(RealBackend, "model", lambda self: object())
    _wire(monkeypatch, tmp_path, seen)

    r = b._execute("donor_00", prefix=None, step_limit=None)
    assert seen[-1] == [] and r["prefix_injected"] is False

    frozen = [{"role": "system"}, {"role": "user", "content": "<pr_description>fix</pr_description>"},
              {"role": "assistant"}, {"role": "tool"}]
    monkeypatch.setattr(RealBackend, "_restore",
                        lambda self, d, extra, ls: (frozen, {"step_dir": "s",
                                                             "tracked_diff_hash": "T",
                                                             "horizon": 24,
                                                             "donor_run_id": d}))
    r2 = b._execute("cont", prefix="donor_00", step_limit=226, horizon=24)
    assert seen[-1] == frozen
    assert r2["prefix_injected"] is True and r2["prefix_messages"] == 4
    assert r2["archive"]["horizon"] == 24


def test_execute_records_container_digest_hashes_commands_and_status(tmp_path, monkeypatch):
    b = _preflighted(tmp_path)
    monkeypatch.setattr(RealBackend, "image_digest", lambda self: "sha256:beef")
    monkeypatch.setattr(RealBackend, "model", lambda self: object())
    _wire(monkeypatch, tmp_path, [])
    r = b._execute("donor_00", prefix=None, step_limit=None)
    assert r["container_id"] == "container-abc123"
    assert r["image_digest"] == "sha256:beef" and r["image"] == P.IMAGE
    assert r["start_tracked"] == "T" and r["start_workspace"] == "W"
    assert r["commands"] == ["pytest -q"]
    assert r["exit_status"] == "Submitted"


def test_every_transport_attempt_is_summed_into_the_record(tmp_path, monkeypatch):
    msgs = [{"role": "assistant", "extra": {"actions": [{"command": "a"}],
             "transport_attempts": 2,
             "transport_events": [{"attempt": 1, "outcome": "exception"},
                                  {"attempt": 2, "outcome": "ok"}]}},
            {"role": "assistant", "extra": {"actions": [{"command": "b"}],
             "transport_attempts": 1,
             "transport_events": [{"attempt": 1, "outcome": "ok"}]}}]
    b = _preflighted(tmp_path)
    monkeypatch.setattr(RealBackend, "image_digest", lambda self: "sha256:1")
    monkeypatch.setattr(RealBackend, "model", lambda self: object())
    _wire(monkeypatch, tmp_path, [], messages=msgs)
    r = b._execute("x", prefix=None, step_limit=None)
    assert r["transport_attempts"] == 3
    assert len(r["transport_events"]) == 3


def test_the_same_client_is_reused_for_donor_and_continuation(tmp_path, monkeypatch):
    b = _preflighted(tmp_path)
    client = _compliant_client()
    calls = {"n": 0}
    def one_client(self):
        calls["n"] += 1
        return client
    monkeypatch.setattr(RealBackend, "image_digest", lambda self: "sha256:1")
    monkeypatch.setattr(RealBackend, "model", one_client)
    monkeypatch.setattr(RealBackend, "_restore",
                        lambda self, d, e, ls: ([{"role": "system"}, {"role": "user"}],
                                                {"step_dir": "s", "horizon": 16}))
    _wire(monkeypatch, tmp_path, [])
    b._execute("donor_00", prefix=None, step_limit=None)
    b._execute("cont", prefix="donor_00", step_limit=234, horizon=16)
    assert calls["n"] == 2              # asked twice, and model() memoises


# ── 13. restoring a fork root ──
def test_missing_archive_is_an_integrity_stop(tmp_path):
    b = be(tmp_path)
    with pytest.raises(IntegrityStop) as e:
        b._restore("donor_00", {"horizon": 16}, lambda p: {})
    assert e.value.stage == "restore" and "no archive" in e.value.detail


def test_a_spec_without_a_horizon_is_an_integrity_stop(tmp_path):
    b = be(tmp_path)
    with pytest.raises(IntegrityStop) as e:
        b._restore("donor_00", {}, lambda p: {})
    assert "no horizon" in e.value.detail


def test_an_archived_step_without_a_prefix_is_an_integrity_stop(tmp_path):
    d = tmp_path / "raw" / "donor_00.archive" / "step_0016"
    d.mkdir(parents=True)
    b = be(tmp_path)
    with pytest.raises(IntegrityStop) as e:
        b._restore("donor_00", {"horizon": 16}, lambda p: {"messages": []})
    assert "no message prefix" in e.value.detail


def test_a_resolvable_archive_returns_the_frozen_prefix(tmp_path):
    d = tmp_path / "raw" / "donor_00.archive" / "step_0024"
    d.mkdir(parents=True)
    b = be(tmp_path)
    msgs, state = b._restore("donor_00", {"horizon": 24},
                             lambda p: {"messages": [{"role": "system"}],
                                        "tracked_diff_hash": "T"})
    assert msgs == [{"role": "system"}]
    assert state["horizon"] == 24 and state["tracked_diff_hash"] == "T"
    assert state["step_dir"].endswith("step_0024")


# ── 14. identity drift now covers task, image and digest ──
@pytest.mark.parametrize("field", ["task", "image", "image_digest"])
def test_task_and_image_cannot_drift(tmp_path, field):
    b = be(tmp_path)
    b._identity = {"endpoint": "e", "vllm_pid": "1", "gpu": "g", "hostname": "h",
                   "model_id": "m", "revision": "r", "task": P.TASK,
                   "image": P.IMAGE, "image_digest": "sha256:1"}
    with mock.patch.object(RealBackend, "identity",
                           return_value=dict(b._identity) | {field: "other"}):
        with pytest.raises(IntegrityStop) as e:
            b.assert_same_serving_process()
    assert e.value.stage == "serving_identity"


# ── 15. preflight runs before donor 0, or nothing runs ──
def test_execute_refuses_before_preflight(tmp_path):
    b = be(tmp_path)
    assert b._identity is None
    with pytest.raises(IntegrityStop) as e:
        b._execute("donor_00", prefix=None, step_limit=None)
    assert e.value.stage == "preflight"


def test_preflight_resolves_digest_lock_and_client(tmp_path, monkeypatch):
    b = be(tmp_path)
    monkeypatch.setattr(RealBackend, "image_digest",
                        lambda self: setattr(self, "_image_digest", "sha256:aa")
                        or "sha256:aa")
    monkeypatch.setattr(RealBackend, "model", lambda self: _compliant_client())
    ident = b.preflight()
    assert ident["image_digest"] == "sha256:aa"
    assert ident["dependency_lock_sha256"] and len(ident["dependency_lock_sha256"]) == 16
    assert ident["protocol_hash"] == P.protocol_hash()
    assert ident["task"] == P.TASK and ident["image"] == P.IMAGE


def test_preflight_stops_if_the_dependency_lock_is_missing(tmp_path, monkeypatch):
    from experiments.coding import c2h_protocol as CP
    monkeypatch.setattr(CP, "DEP_LOCK", "inference/does-not-exist.txt")
    b = be(tmp_path)
    with pytest.raises(IntegrityStop) as e:
        b.preflight()
    assert e.value.stage == "dependency_lock"


def test_preflight_stops_if_the_target_is_not_the_registered_one(tmp_path):
    b = be(tmp_path)
    b.image = "somethingelse:latest"
    with pytest.raises(IntegrityStop) as e:
        b.preflight()
    assert e.value.stage == "registered_target"


def test_the_fingerprint_covers_everything_the_audit_requires(tmp_path, monkeypatch):
    monkeypatch.setattr(RealBackend, "image_digest",
                        lambda self: setattr(self, "_image_digest", "d") or "d")
    monkeypatch.setattr(RealBackend, "model", lambda self: _compliant_client())
    ident = be(tmp_path).preflight()
    for field in ("hostname", "boot_id", "machine", "gpu", "vllm_pid", "endpoint",
                  "model_id", "revision", "task", "image", "image_digest",
                  "dependency_lock_sha256", "protocol_hash"):
        assert field in ident, f"{field} missing from the session fingerprint"


def test_session_binding_compares_every_recorded_field(tmp_path):
    """A new fingerprint field must not escape the comparison by being absent
    from a hard-coded list."""
    from experiments.coding.c2h_budget import RunLog as RL
    from experiments.coding.run_c2h import FailClosed, bind_session
    log = RL(tmp_path / "l.jsonl")
    bind_session(log, {"a": 1, "b": 2})
    with pytest.raises(FailClosed):
        bind_session(log, {"a": 1, "b": 2, "c": 3})      # extra field differs
