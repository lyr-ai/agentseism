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

import os
import re
import subprocess
import tempfile
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


OPT_IN_DOCKER_MODULES = ("tests/test_docker_integration.py",
                         "tests/test_real_cli_docker.py",
                         "tests/test_f3_cli_docker.py")


def test_the_harness_mock_reports_the_frozen_counts():
    """The mock stands in for pytest during harness scenarios. When
    EXPECTED_SKIPPED moved and the mock kept its own default of 9, every
    scenario failed step 5 -- the gate working against a stale fixture. The
    numbers are tied together here so that cannot recur."""
    harness = (ROOT / "inference/tests/test_stage_b_preflight.sh").read_text()
    m = re.search(r"^MOCK_PYTEST_SKIPPED=(\d+)$", harness, re.M)
    assert m, "the harness does not export a skip count"
    assert m.group(1) == const("EXPECTED_SKIPPED")
    mock = (ROOT / "inference/tests/mock_stage_b_env.sh").read_text()
    assert "MOCK_PYTEST_SKIPPED:?" in mock, \
        "the mock has a default skip count again; it must take the harness's"


def test_the_skipped_count_is_exactly_the_opt_in_docker_tests():
    """Skips are deliberate and enumerated, not incidental.

    Counted from the `@requires_docker` decorations themselves, across every
    opt-in module -- an earlier version counted one file and silently stopped
    accounting for the skips when a second appeared.
    """
    import os
    assert not os.environ.get("AGENTSEISM_DOCKER_TESTS"), \
        "run the default suite without the opt-in to check the skip count"
    marked = sum((ROOT / m).read_text().count("@requires_docker")
                 for m in OPT_IN_DOCKER_MODULES)
    assert int(const("EXPECTED_SKIPPED")) == marked, (
        f"EXPECTED_SKIPPED={const('EXPECTED_SKIPPED')} but "
        f"{marked} tests are marked across {OPT_IN_DOCKER_MODULES}")


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


def test_the_preflight_can_parse_the_hashes_out_of_resolve_only():
    """The script's own extraction, applied to the CLI's real output.

    These were coupled by nothing. Adding a word to the front of the
    `protocol ...` line made `sed -nE 's/^protocol ([0-9a-f]+).*/\\1/p'` yield
    an **empty** hash, so the preflight died with `protocol hash  != frozen
    b7af66ca3ab783ab` -- a message whose blank is easy to read past. Only the
    shell harness caught it; a format contract deserves a cheap test too.
    """
    script = (ROOT / "inference/stage_b_preflight.sh").read_text()
    exprs = {}
    for field in ("ph", "oh", "cells"):
        m = re.search(rf"^\s*{field}=\"\$\(sed -nE '(.+?)' ", script, re.M)
        assert m, f"cannot find the {field} extraction in the script"
        exprs[field] = m.group(1)

    r = subprocess.run([sys.executable, "-m", "agentseism.pilot",
                        "--resolve-only"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120,
                       env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert r.returncode == 0, r.stderr[-2000:]

    def extract(expr: str) -> str:
        out = subprocess.run(["sed", "-nE", expr], input=r.stdout,
                             capture_output=True, text=True)
        return out.stdout.splitlines()[0] if out.stdout.splitlines() else ""

    assert extract(exprs["ph"]) == const("PROTOCOL_HASH")
    assert extract(exprs["oh"]) == const("ORDER_HASH")
    assert extract(exprs["cells"]) == const("EXPECTED_CELLS")


def test_the_smoke_marker_imports_from_outside_the_repo():
    """Two paid hosts died here, at the same step, after a passing smoke.

    The marker runs after the `cd -` that closes the smoke block, so its
    PYTHONPATH must name both the package root and the repository root. Inside
    the repo `python3 -` puts cwd on sys.path, which hid the omission
    completely -- and hid it again after a fix that supplied only `$REPO/src`,
    because `agentseism` then imported and `experiments` did not.

    So the test runs the imports the marker performs, from a directory that is
    not the repository, with exactly the PYTHONPATH the script sets.
    """
    m = re.search(r'^\s*PYTHONPATH="([^"]+)" RUN_LOG=[^\n]*mark smoke_completed',
                  (ROOT / "inference/stage_b_preflight.sh").read_text(), re.M)
    assert m, "the smoke marker's PYTHONPATH is not where this test expects it"
    pythonpath = m.group(1).replace("$REPO", str(ROOT))

    r = subprocess.run(
        [sys.executable, "-c",
         "from agentseism.budget import RunLog; import agentseism; print('ok')"],
        cwd=tempfile.gettempdir(),          # deliberately not the repository
        env={**os.environ, "PYTHONPATH": pythonpath},
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (
        f"the marker's imports fail from outside the repo:\n{r.stderr[-1500:]}")
    assert "ok" in r.stdout
