"""The preflight script's frozen constants, checked against their sources.

Every one of these is a number or a string typed into a shell script by hand
and expected to agree with something else in the tree. Two have already
drifted and cost a stopped run each: a short sha compared against a full one,
and a test count left at 504 while the suite grew to 515 -- a script that
would have rejected the very tree it was shipped in.

A constant nothing checks is a constant that is already wrong and has not been
run yet.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "inference/stage_b_preflight.sh"


def const(name: str) -> str:
    """The value of a top-level `NAME="value"` or `NAME=value` assignment."""
    m = re.search(rf'^{name}="?([^"\n#]+?)"?\s*(?:#.*)?$',
                  SCRIPT.read_text(), re.M)
    assert m, f"{name} is not assigned in {SCRIPT.name}"
    return m.group(1).strip()


def test_the_protocol_hash_matches_the_protocol():
    assert const("PROTOCOL_HASH") == P.protocol_hash()


def test_the_order_hash_matches_the_protocol():
    assert const("ORDER_HASH") == P.ORDER_HASH == P.order_hash(P.build_order())


def test_the_cell_count_matches_the_protocol():
    assert int(const("EXPECTED_CELLS")) == P.CELLS == 18


def test_the_task_count_matches_the_protocol():
    assert int(const("TASKS_WANTED")) == P.TASK_COUNT


def test_the_expected_test_count_is_what_the_suite_actually_collects():
    """The one that already broke: the script froze 504 and the suite was 515."""
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                        "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:]
    m = re.search(r"(\d+) tests? collected", r.stdout)
    assert m, r.stdout[-2000:]
    # The script compares against *passed*, and some tests are collected but
    # skipped by design, so the two frozen numbers must sum to the collection.
    collected = int(m.group(1))
    assert int(const("EXPECTED_TESTS")) + int(const("EXPECTED_SKIPPED")) \
        == collected


def test_the_skipped_count_is_the_opt_in_docker_suite():
    """Skips are deliberate and enumerated, not incidental."""
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                        "-p", "no:cacheprovider",
                        "tests/test_docker_integration.py"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    n = int(re.search(r"(\d+) tests? collected", r.stdout).group(1))
    # every Docker-marked test skips without the opt-in
    import os
    assert not os.environ.get("AGENTSEISM_DOCKER_TESTS"), \
        "run the default suite without the opt-in to check the skip count"
    assert int(const("EXPECTED_SKIPPED")) <= n


def test_the_serving_constants_match_the_serving_config():
    cfg = yaml.safe_load((ROOT / const("SERVING_CONFIG")).read_text())
    assert const("EXPECTED_MODEL") == cfg["model"]["id"]
    assert const("EXPECTED_REVISION") == cfg["model"]["revision"]
    assert int(const("EXPECTED_MAX_MODEL_LEN")) == cfg["serving"]["max_model_len"]


def test_the_serving_config_still_carries_the_three_parser_keys():
    """Their absence, while the file's header claimed them, is what made the
    server accept no tool call in an earlier session."""
    cfg = yaml.safe_load((ROOT / const("SERVING_CONFIG")).read_text())["serving"]
    assert cfg["enable_auto_tool_choice"] is True
    assert cfg["tool_call_parser"] == "qwen3_coder"
    assert cfg["reasoning_parser"] == "qwen3"


def test_the_baseline_constants_match_the_frozen_run_log():
    import json
    rows = [json.loads(l) for l in
            (ROOT / "data/runs/pilot/run.jsonl").read_text().splitlines() if l.strip()]
    base = next(r for r in rows if r["kind"] == "billing_baseline")
    assert float(const("BASELINE_USD")) == base["current_total"]
    assert const("BASELINE_CURRENCY") == base["currency"]
    assert const("BASELINE_PERIOD") == base["billing_period"]


def test_the_budget_constants_match_the_registration():
    assert float(const("BASELINE_USD")) > 0
    # the stops themselves live in the protocol, and the script never restates
    # them -- assert that it does not
    body = SCRIPT.read_text()
    for n in ("20", "25", "30"):
        assert f'NO_NEW_BLOCK={n}' not in body and f'ABSOLUTE={n}' not in body
