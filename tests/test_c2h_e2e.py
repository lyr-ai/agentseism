"""C2-H end to end through a fake backend. No model, no vLLM, no network.

Every terminal state and every fail-closed condition is driven by injected
donor generation and continuation functions, so the control flow that will run
on a rented GPU is the control flow exercised here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.coding import c2h_protocol as P
from experiments.coding.c2h_budget import Budget, RunLog, write_atomic
from experiments.coding.run_c2h import (
    FailClosed, classify, completed_specs, execute, freeze_manifest,
    incomplete_blocks, plan,
)

FP = {"hostname": "h1", "boot_id": "b1", "machine": "x86_64",
      "gpu": "GPU-1", "vllm_pid": "42"}


def donor_seq(pattern):
    """A frozen checker standing in: label by position in `pattern`."""
    return lambda seed, run_id: pattern[seed % len(pattern)]


def backend_ok(spec):
    return {"exit_status": "Submitted", "correct": spec["horizon"] != 16}


def paying(out, amounts):
    """A billing entry per call, walking `amounts`; the operator's readings."""
    it = iter(amounts)
    b = Budget(RunLog(Path(out) / "run.jsonl"))
    def top_up():
        b.record_reading(next(it, amounts[-1]))
    return top_up


def run(out, pattern=("FAIL", "PASS"), backend=backend_ok, amounts=(1.0,),
        fingerprint=None):
    """Drive `execute`, topping up a reading before every budget check."""
    log = RunLog(Path(out) / "run.jsonl")
    b = Budget(log)
    it = iter(amounts)
    last = [amounts[0]]

    def gen(seed, run_id):
        return donor_seq(pattern)(seed, run_id)

    def wrapped(spec):
        return backend(spec)

    # A reading is consumed per authorised checkpoint, so pre-load generously;
    # the state machine still refuses a stale one.
    orig = b.check
    def check(cp, idx=None):
        v = next(it, last[0]); last[0] = v
        b.record_reading(v)
        return orig(cp, idx)
    b.check = check                                     # noqa: SLF001
    import experiments.coding.run_c2h as R
    real_budget = R.Budget
    R.Budget = lambda _log: b
    try:
        return execute(Path(out), gen, wrapped, fingerprint or FP)
    finally:
        R.Budget = real_budget


# ── 1. the happy path ──
def test_complete_72_is_the_only_state_that_allows_a_verdict(tmp_path):
    rep = run(tmp_path)
    assert rep["state"] == "complete_72"
    assert rep["verdict_allowed"] is True
    assert rep["protocol_hash"] == P.protocol_hash()
    log = RunLog(tmp_path / "run.jsonl")
    assert len(completed_specs(log)) == 72
    assert incomplete_blocks(log) == []
    assert len([r for r in log.read() if r["kind"] == "block_end"]) == 24


def test_blocks_run_in_the_frozen_order(tmp_path):
    run(tmp_path)
    log = RunLog(tmp_path / "run.jsonl")
    started = [r["block_index"] for r in log.read() if r["kind"] == "block_start"]
    assert started == list(range(24))
    arms = [r["arm"] for r in log.read() if r["kind"] == "block_start"]
    assert arms == ["FAIL"] * 12 + ["PASS"] * 12


# ── 2. donor yield ──
def test_donor_yield_feasibility_stop(tmp_path):
    rep = run(tmp_path, pattern=("PASS",))
    assert rep["state"] == "donor_yield_feasibility_stop"
    assert rep["verdict_allowed"] is False
    log = RunLog(tmp_path / "run.jsonl")
    assert sum(1 for r in log.read() if r["kind"] == "donor") == P.DONOR_CAP
    assert not [r for r in log.read() if r["kind"] == "block_start"]
    assert not (tmp_path / "manifest.json").exists()


# ── 3. the three budget thresholds ──
@pytest.mark.parametrize("amounts,expect_blocks", [
    ((1.0, 1.0, 85.0), 0),     # no_new_block before the first block
    ((1.0, 90.0), 0),          # stop_stage at after_donors
    ((100.0,), 0),             # absolute at after_setup
])
def test_budget_thresholds_censor_the_run(tmp_path, amounts, expect_blocks):
    rep = run(tmp_path, amounts=amounts)
    assert rep["verdict_allowed"] is False
    assert rep["state"] in ("budget_censored_feasibility_run",
                            "integrity_stop")
    log = RunLog(tmp_path / "run.jsonl")
    assert len([r for r in log.read() if r["kind"] == "block_start"]) == expect_blocks


def test_a_mid_run_threshold_censors_but_keeps_finished_blocks(tmp_path):
    rep = run(tmp_path, amounts=(1.0, 1.0, 1.0, 1.0, 1.0, 86.0))
    assert rep["state"] == "budget_censored_feasibility_run"
    assert rep["verdict_allowed"] is False
    assert 0 < rep["completed"] < 72
    assert incomplete_blocks(RunLog(tmp_path / "run.jsonl")) == []


# ── 4. interruption ──
def test_an_interrupted_block_is_incomplete_not_partially_credited(tmp_path):
    calls = {"n": 0}
    def flaky(spec):
        calls["n"] += 1
        if calls["n"] == 3:                     # mid-way through block 0
            raise KeyboardInterrupt("killed")
        return backend_ok(spec)
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, backend=flaky)
    log = RunLog(tmp_path / "run.jsonl")
    assert incomplete_blocks(log) == [0]
    assert completed_specs(log) == set()        # two results written, zero credited
    assert len([r for r in log.read() if r["kind"] == "continuation"]) == 2
    pl = plan(json.loads((tmp_path / "manifest.json").read_text())["donors"])
    rep = classify(log, pl)
    assert rep["state"] == "budget_censored_feasibility_run"
    assert rep["verdict_allowed"] is False
    assert rep["incomplete_blocks"] == [0]


def test_resume_reruns_the_incomplete_block(tmp_path):
    calls = {"n": 0}
    def flaky(spec):
        calls["n"] += 1
        if calls["n"] == 3:
            raise KeyboardInterrupt
        return backend_ok(spec)
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, backend=flaky)
    rep = run(tmp_path)                          # same session
    assert rep["state"] == "complete_72"
    assert incomplete_blocks(RunLog(tmp_path / "run.jsonl")) == []


# ── 5. repeated start, and cross-session resume ──
def test_second_run_in_the_same_session_is_idempotent(tmp_path):
    a = run(tmp_path); b = run(tmp_path)
    assert a["state"] == b["state"] == "complete_72"
    assert a["manifest_hash"] == b["manifest_hash"]
    log = RunLog(tmp_path / "run.jsonl")
    assert len([r for r in log.read() if r["kind"] == "manifest_frozen"]) == 1
    assert len([r for r in log.read() if r["kind"] == "block_end"]) == 24


@pytest.mark.parametrize("field", ["hostname", "boot_id", "gpu", "vllm_pid"])
def test_cross_session_resume_is_refused(tmp_path, field):
    run(tmp_path)
    with pytest.raises(FailClosed, match="not the session"):
        run(tmp_path, fingerprint=FP | {field: "different"})


def test_a_restarted_serving_process_is_a_different_session(tmp_path):
    """Deliberate: same machine, new vLLM pid, still refused. C2-H is one
    serving process, so a restart ends the session it defines."""
    run(tmp_path)
    with pytest.raises(FailClosed):
        run(tmp_path, fingerprint=FP | {"vllm_pid": "9999"})


# ── 6. manifest immutability ──
def test_manifest_change_after_freezing_fails_closed(tmp_path):
    run(tmp_path)
    log = RunLog(tmp_path / "run.jsonl")
    other = [{"arm": "FAIL", "donor_id": f"x{i}", "acquisition_index": i, "run_id": f"x{i}"}
             for i in range(4)]
    other += [{"arm": "PASS", "donor_id": f"y{i}", "acquisition_index": 9 + i, "run_id": f"y{i}"}
              for i in range(4)]
    with pytest.raises(FailClosed, match="manifest changed"):
        freeze_manifest(log, tmp_path, other)


def test_donor_order_changes_the_manifest_hash(tmp_path):
    run(tmp_path)
    m = json.loads((tmp_path / "manifest.json").read_text())
    d = list(m["donors"]); d[0], d[1] = d[1], d[0]
    assert plan(d)["manifest_hash"] != m["manifest_hash"]


# ── 7. exactly the descriptive 36 ──
def test_completing_exactly_the_36_is_still_censored(tmp_path):
    rep = run(tmp_path)
    pl = plan(json.loads((tmp_path / "manifest.json").read_text())["donors"])
    log = RunLog(tmp_path / "run.jsonl")
    sub = classify(_log_with_only(log, tmp_path, P.subset_36(pl["specs"])), pl)
    assert sub["state"] == "budget_censored_feasibility_run"
    assert sub["verdict_allowed"] is False
    assert "coincides with the descriptive 36" in sub["reason"]
    assert rep["state"] == "complete_72"        # the real run was not affected


def _log_with_only(log, tmp_path, specs):
    """A log in which exactly `specs` completed, to classify a hypothetical."""
    fake = RunLog(tmp_path / "hypothetical.jsonl")
    fake.append("session", fingerprint=FP, protocol_hash=P.protocol_hash())
    fake.append("manifest_frozen", manifest_hash="x", order_hash="y")
    fake.append("block_start", block_index=0, specs=[s["run_id"] for s in specs])
    fake.append("block_end", block_index=0, specs=[s["run_id"] for s in specs])
    return fake


# ── 8. artifact atomicity ──
def test_every_artifact_carries_a_sha256(tmp_path):
    run(tmp_path)
    for name in ("manifest.json", "report.json", "block_00.json"):
        f = tmp_path / name
        assert f.exists() and (tmp_path / (name + ".sha256")).exists()
        import hashlib
        want = hashlib.sha256(f.read_text().encode()).hexdigest()
        assert (tmp_path / (name + ".sha256")).read_text().split()[0] == want


def test_atomic_write_leaves_no_partial_file(tmp_path):
    p = tmp_path / "a.json"
    write_atomic(p, '{"complete": true}')
    assert json.loads(p.read_text())["complete"] is True
    assert not list(tmp_path.glob("*.tmp"))


def test_a_failed_write_does_not_replace_a_good_artifact(tmp_path, monkeypatch):
    p = tmp_path / "a.json"
    write_atomic(p, '{"v": 1}')
    import os as _os
    monkeypatch.setattr(_os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        write_atomic(p, '{"v": 2}')
    assert json.loads(p.read_text())["v"] == 1      # the old one still stands


def test_block_artifacts_match_the_log(tmp_path):
    run(tmp_path)
    log = RunLog(tmp_path / "run.jsonl")
    for r in [x for x in log.read() if x["kind"] == "block_end"]:
        f = tmp_path / f"block_{r['block_index']:02d}.json"
        import hashlib
        assert hashlib.sha256(f.read_text().encode()).hexdigest() == r["file_sha256"]
        assert [x["run_id"] for x in json.loads(f.read_text())["results"]] == r["specs"]
