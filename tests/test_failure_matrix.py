"""One test per historical failure, rebuilt from the frozen logs.

Gate 9's aborted attempts and hosts 2-4 each cost real money to discover. The
point of this file is that none of them can be rediscovered on a GPU: every
row of `docs/FAILURE_MATRIX.md` has a check here or names the gate that holds
it.

The causes are read from `paper/GATE9_EXECUTION_LOG.md` and
`paper/PILOT_EXECUTION_LOG.md`, which are frozen, rather than recalled.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P
from agentseism import real_backend as RB

ROOT = Path(__file__).resolve().parents[1]
GATE9 = (ROOT / "paper/GATE9_EXECUTION_LOG.md").read_text()
PILOTLOG = (ROOT / "paper/PILOT_EXECUTION_LOG.md").read_text()
SCRIPT = (ROOT / "inference/stage_b_preflight.sh").read_text()
CFG = yaml.safe_load((ROOT / "inference/configs/model_h2.yaml").read_text())


# ── the history is on disk, not in anyone's memory ──
def test_gate9_recorded_exactly_three_aborted_attempts():
    rows = re.findall(r"^\| [123] \| 2026-09-20 \d\d:\d\d \|", GATE9, re.M)
    assert len(rows) == 3, f"{len(rows)} aborted attempts in the frozen log"
    assert "Three invocations were stopped before producing results" in GATE9


def test_every_gate9_attempt_produced_zero_responses_and_no_artifact():
    for n in (1, 2, 3):
        row = re.search(rf"^\| {n} \|.*$", GATE9, re.M).group(0)
        assert row.rstrip().endswith("| 0 | no |"), row[-40:]


# ── G9-1 and G9-2: the serving config must carry the parser keys ──
def test_the_three_parser_keys_are_in_the_serving_config():
    s = CFG["serving"]
    assert s["enable_auto_tool_choice"] is True
    assert s["tool_call_parser"] == "qwen3_coder"
    assert s["reasoning_parser"] == "qwen3"


def test_preflight_verifies_the_parser_flags_on_the_live_command_line():
    for flag in ("--enable-auto-tool-choice", "--tool-call-parser qwen3_coder",
                 "--reasoning-parser qwen3"):
        assert flag in SCRIPT, flag


# ── G9-3 and host 4: cost accounting discards a successful response ──
def test_the_cost_variable_is_registered_for_the_pilot():
    assert P.COST_ENV == {"MSWEA_COST_TRACKING": "ignore_errors"}
    assert P.COST_TRACKING == "ignore_errors"


def test_the_pilot_sets_cost_tracking_on_the_model_config():
    """The field, not only the variable: it is read at import time."""
    cfg = RB.BackendConfig(image_digests={}, work_dir=Path("."),
                           model_base_url="http://127.0.0.1:8000/v1",
                           model_name="Qwen/Qwen3.6-27B-FP8",
                           model_revision="x")
    assert RB.model_config(cfg, P.HINTS["full"])["cost_tracking"] == "ignore_errors"


def test_the_shell_exports_the_cost_variable_before_any_python():
    lines = SCRIPT.splitlines()
    at = next(i for i, l in enumerate(lines)
              if l.startswith("export MSWEA_COST_TRACKING="))
    first_py = next(i for i, l in enumerate(lines)
                    if "venv-eval/bin/python" in l or "python3 -" in l)
    assert at < first_py


def test_every_runner_in_the_tree_sets_the_cost_variable():
    """Gate 9 fixed two runners; the pilot backend was a third that never
    inherited it. A fourth must not repeat that."""
    runners = {
        "experiments/coding/gate9.py": "MSWEA_COST_TRACKING",
        "experiments/coding/c2h_backend.py": "MSWEA_COST_TRACKING",
        "src/agentseism/real_backend.py": "cost_tracking",
    }
    for path, token in runners.items():
        body = (ROOT / path).read_text()
        assert token in body, f"{path} does not set the cost policy"


# ── G9 deployment: a public, unauthenticated endpoint ──
def test_the_serving_host_is_loopback():
    """`start_vllm.sh` once hardcoded 0.0.0.0, which on a public-IP VM
    publishes an unauthenticated endpoint."""
    assert CFG["serving"]["host"] in ("127.0.0.1", "localhost")
    start = (ROOT / "inference/start_vllm.sh").read_text()
    # Code, not prose: the file explains *why* 0.0.0.0 is wrong, and an
    # assertion that forbids the string outright flags the explanation.
    for bad in ("--host 0.0.0.0", "HOST=0.0.0.0", 'HOST="0.0.0.0"'):
        assert bad not in start, f"the bind address is hardcoded again: {bad}"
    assert "HOST=${HOST:-127.0.0.1}" in start


# ── G9 deployment: pins that never resolved in a clean environment ──
@pytest.mark.parametrize("pkg", ["mini-swe-agent==2.4.6", "swebench==5.0.2",
                                 "pytest=="])
def test_the_eval_lock_pins_what_the_suite_and_evaluator_need(pkg):
    lock = (ROOT / "inference/requirements-eval.lock.txt").read_text()
    assert pkg in lock, f"{pkg} is not pinned"


# ── host 2: READY with no runner ──
def test_a_missing_runner_cannot_report_ready(monkeypatch):
    monkeypatch.delitem(RB.__dict__, "run_cell")
    with pytest.raises(RB.BackendUnavailable):
        RB.build(dry_run=True)


# ── host 3: a bare model id reached LiteLLM ──
def test_a_bare_model_id_is_addressed_before_it_reaches_the_client():
    assert P.transport_model("Qwen/Qwen3.6-27B-FP8") == \
        "openai/Qwen/Qwen3.6-27B-FP8"


# ── every registered environment value is exported before Python ──
def test_every_registered_env_value_is_exported_by_the_script():
    for name, value in {**P.RETRY_ENV, **P.COST_ENV}.items():
        assert f"export {name}={value}" in SCRIPT, \
            f"{name} is registered but the script does not export it"


def test_the_backend_asserts_every_registered_env_value(monkeypatch):
    for name in {**P.RETRY_ENV, **P.COST_ENV}:
        monkeypatch.setenv(name, "wrong")
    with pytest.raises(RB.BackendUnavailable):
        RB.assert_retry_env()
    with pytest.raises(RB.BackendUnavailable):
        RB.assert_cost_env()
