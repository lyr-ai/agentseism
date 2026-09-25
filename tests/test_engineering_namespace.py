"""`engineering` is an execution namespace, not a third registered experiment.

The distinction has to be enforced, because the reason it exists is to prove
the production path works *without* that proof quietly becoming experimental
evidence. Two failure modes are equally bad: evidence that impersonates a
registered experiment, and a provenance fix that smuggles in a budget reset.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentseism import engineering_protocol as E   # noqa: E402
from agentseism import f3_protocol as F            # noqa: E402
from agentseism import pilot                       # noqa: E402
from agentseism import pilot_protocol as P         # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "inference/stage_b_preflight.sh").read_text()
CLOSED_HASHES = ("b7af66ca3ab783ab", "cfe8856c9c9167b5",
                 "c145bebf3e39bc7d", "a83650caeae31ff6")


def _const(name: str) -> str:
    m = re.search(rf'^{name}="?([^"\n]+)"?$', SCRIPT, re.M)
    assert m, f"{name} not in the preflight"
    return m.group(1)


# ── exactly one cell ──
def test_it_is_exactly_one_cell():
    cells = E.SPEC.verify([E.TASK])
    assert len(cells) == 1
    assert cells[0]["arm"] == "baseline"
    assert E.SPEC.task_count == E.SPEC.replicates == 1


def test_one_arm_so_there_is_nothing_to_compare():
    """Two arms would invite a comparison a single execution cannot support."""
    assert len(E.ENGINEERING_ARMS) == 1
    assert E.SPEC.cell_count == 1


# ── not experimental evidence, and the file says so ──
def test_the_spec_declares_itself_non_experimental():
    assert E.SPEC.experimental_evidence is False
    assert P.SPEC.experimental_evidence is True
    assert F.SPEC.experimental_evidence is True


def test_every_artifact_carries_the_flag(tmp_path):
    cell = E.SPEC.verify([E.TASK])[0]
    art = pilot.artifact(cell, {"termination": P.COMPLETED}, {}, False, E.SPEC)
    assert art["experimental_evidence"] is False
    assert art["experiment"] == "engineering"


def test_the_flag_is_on_the_file_not_the_directory():
    """A copy that leaves data/runs/engineering/ still says what it is."""
    import inspect
    src = inspect.getsource(pilot.artifact)
    assert '"experimental_evidence": spec.experimental_evidence' in src


# ── it does not impersonate pilot or F3 ──
def test_it_carries_none_of_the_registered_experiments_hashes():
    for h in CLOSED_HASHES:
        assert E.SPEC.protocol_hash != h
        assert E.SPEC.order_hash != h


def test_it_neither_reads_nor_writes_the_closed_logs():
    assert _const("ENG_RUN_LOG") == "data/runs/engineering/run.jsonl"
    assert E.__doc__ and "data/runs/engineering/" in E.__doc__
    # It carries the figure as a constant rather than reading the closed F3
    # log. Asserting the string is absent would fail on the docstring that
    # explains the choice, so the accurate claim is that a values-only module
    # does no file I/O at all -- it cannot read that log, or any other.
    import ast
    tree = ast.parse(Path(E.__file__).read_text())
    calls = {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not ({"open", "Path", "RunLog"} & calls), calls
    attrs = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not ({"read_text", "read_bytes", "write_text"} & attrs), attrs


def test_its_output_directory_is_its_own():
    assert 'PILOT_DIR="$WORK/$EXPERIMENT"' in SCRIPT


# ── the budget origin is shared, not reset ──
def test_it_does_not_establish_a_new_billing_origin():
    """The load-bearing invariant.

    Execution identity and spend accounting are different things. A fresh
    origin here would erase every dollar already spent from the count -- a
    budget reset wearing a provenance fix as a disguise.
    """
    assert E.BILLING_ORIGIN_USD == 16.88
    assert _const("ENG_BASELINE_USD") == _const("F3_BASELINE_USD")
    assert _const("ENG_BASELINE_PERIOD") == _const("F3_BASELINE_PERIOD")
    assert _const("ENG_BASELINE_CURRENCY") == _const("F3_BASELINE_CURRENCY")


def test_the_anchored_log_records_the_same_origin_once():
    log = ROOT / "data/runs/engineering/run.jsonl"
    base = [json.loads(l) for l in log.read_text().splitlines()
            if '"billing_baseline"' in l]
    assert len(base) == 1
    assert base[0]["current_total"] == E.BILLING_ORIGIN_USD
    assert "ANCHOR, NOT A NEW ORIGIN" in base[0]["note"]


def test_the_thresholds_are_cumulative_not_marginal():
    """Sized above what the shared origin has already spent, so they fire on
    what engineering does rather than on history."""
    assert (E.WARNING_USD, E.NO_NEW_BLOCK_USD, E.ABSOLUTE_LIMIT_USD) == \
        (9.0, 11.0, 13.0)
    assert E.WARNING_USD > 2.94


# ── the CLIs accept it, and the machinery is shared ──
def test_all_three_clis_accept_the_namespace():
    assert set(pilot.SPECS) == {"pilot", "f3", "engineering"}
    assert pilot.SPECS["engineering"] is E.SPEC


def test_the_task_is_registered_not_drawn():
    assert E.SPEC.registered_task == E.TASK
    assert _const("ENG_TASK") == E.TASK
    assert P.SPEC.registered_task is None


def test_the_preflight_pulls_a_registered_task_whichever_namespace():
    """The branch is keyed on having a registered task, not on being F3 --
    the missing pull cost a host once already."""
    assert 'if [ -n "$EXP_TASK" ]; then' in SCRIPT
    assert "docker_pull('$EXP_TASK'" in SCRIPT


def test_it_reuses_the_production_machinery():
    """Validating a private copy of the production path validates nothing."""
    assert E.ARMS is P.ARMS
    assert E.HINT_SHA256 is P.HINT_SHA256
    assert E.EXIT_STATUS_MAP is P.EXIT_STATUS_MAP
    assert E.RUN_TIMEOUT_SECONDS == P.RUN_TIMEOUT_SECONDS


# ── pilot and F3 are unchanged ──
@pytest.mark.parametrize("spec,ph,oh", [
    (P.SPEC, "b7af66ca3ab783ab", "cfe8856c9c9167b5"),
    (F.SPEC, "c145bebf3e39bc7d", "a83650caeae31ff6"),
])
def test_the_registered_experiments_are_untouched(spec, ph, oh):
    assert spec.protocol_hash == ph
    assert spec.order_hash == oh
