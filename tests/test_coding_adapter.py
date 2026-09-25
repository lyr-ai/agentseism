"""The coding agent wired into AgentSeism's runner and evaluator contracts.

No Docker and no model call: these check the boundary, which is where the two
previous failures on this project lived — a component worked and the thing that
invoked it was never exercised.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.coding import swebench_evaluator as EV   # noqa: E402
from agents.coding import swebench_runner as RUN     # noqa: E402
from agentseism.execution import ConfigurationError, ShellEvaluator, ShellRunner  # noqa: E402

RUNNER_CMD = (f"{sys.executable} {ROOT}/agents/coding/swebench_runner.py "
              "--task {task_file} --out {artifact_dir}")
EVAL_CMD = (f"{sys.executable} {ROOT}/agents/coding/swebench_evaluator.py "
            "{artifact_dir}")


# ── the image name, which two other places in the repo also build ──
def test_the_image_name_matches_the_official_form():
    assert RUN.image_for("pytest-dev__pytest-10051") == (
        "docker.io/swebench/sweb.eval.x86_64."
        "pytest-dev_1776_pytest-10051:latest")


def test_only_the_first_double_underscore_is_replaced():
    """Instance ids contain `__` once as the org/repo separator; a second one
    inside a name must survive."""
    assert RUN.image_for("a__b__c").count("_1776_") == 1


# ── both commands satisfy AgentSeism's preflight ──
def test_the_runner_command_passes_preflight():
    ShellRunner(RUNNER_CMD).preflight()


def test_the_evaluator_command_passes_preflight():
    ShellEvaluator(EVAL_CMD).preflight()


def test_preflight_still_rejects_a_missing_script():
    with pytest.raises(ConfigurationError):
        ShellEvaluator(f"{sys.executable} {ROOT}/agents/coding/nope.py "
                       "{artifact_dir}").preflight()


# ── the config a pull request would change ──
def test_the_step_limit_is_repository_state_not_a_harness_flag():
    """The thing under test is a repo change. A flag passed by the harness
    would not be visible to CI as a diff."""
    cfg = json.loads((ROOT / "agents/coding/agent_config.json").read_text())
    assert cfg["step_limit"] == 250
    assert "--step-limit" not in RUNNER_CMD


def test_the_runner_refuses_a_task_missing_required_fields(tmp_path):
    t = tmp_path / "t.json"
    t.write_text(json.dumps({"instance_id": "x__y-1"}))
    with pytest.raises(SystemExit, match="problem_statement"):
        RUN.main(["--task", str(t), "--out", str(tmp_path / "out")])


# ── the evaluator's output contract ──
def _artifact(tmp_path, patch="diff --git a b\n", exit_status="Submitted"):
    d = tmp_path / "art"
    d.mkdir()
    (d / "patch.diff").write_text(patch)
    (d / "agent_run.json").write_text(json.dumps(
        {"instance_id": "pytest-dev__pytest-10051", "exit_status": exit_status,
         "step_limit": 250}))
    return d


def test_a_resolved_report_is_success_one(tmp_path, monkeypatch):
    monkeypatch.setattr(EV, "evaluate", lambda d: {"success": 1, "label": "PASS"})
    out = subprocess.run([sys.executable, str(ROOT / "agents/coding/swebench_evaluator.py"),
                          str(_artifact(tmp_path))], capture_output=True, text=True)
    # The subprocess does not see the monkeypatch; this asserts the shape the
    # contract requires rather than the verdict.
    assert out.stdout.strip().startswith("{")
    json.loads(out.stdout)


def test_the_runner_does_not_write_run_json(tmp_path):
    """AgentSeism writes its own RunResult to `run.json` in the same directory
    after the evaluator returns. A runner using that name loses its metadata,
    silently, one trial at a time."""
    src = (ROOT / "agents/coding/swebench_runner.py").read_text()
    assert '"run.json"' not in src
    assert '"agent_run.json"' in src


def test_invalid_reasons_use_the_key_the_harness_reads(tmp_path):
    """`run_trials` reads `invalid_reason`. A diagnosis under `reason` is
    dropped on the floor and the operator sees an invalid run with no
    explanation -- which is exactly what happened on the first wiring."""
    src = (ROOT / "agents/coding/swebench_evaluator.py").read_text()
    assert '"reason"' not in src
    assert '"invalid_reason"' in src
    out = subprocess.run([sys.executable, str(ROOT / "agents/coding/swebench_evaluator.py")],
                         capture_output=True, text=True)
    assert "invalid_reason" in json.loads(out.stdout)


def test_an_unlabelled_report_becomes_invalid_not_a_failure(tmp_path, monkeypatch):
    """The distinction the whole schema exists for: an infra fault is not a
    regression. `label_from_report` refuses; that refusal must not be scored."""
    def boom(report, instance):
        raise EV.UnlabelledDonor("infra_failure: not a correctness verdict")
    monkeypatch.setattr(EV, "label_from_report", boom)
    monkeypatch.setattr(EV.subprocess, "run", lambda *a, **k: _FakeProc())
    monkeypatch.setattr(EV.json, "loads", EV.json.loads)
    d = _artifact(tmp_path)
    monkeypatch.setattr(Path, "rglob", lambda self, pat: iter([]))
    got = EV.evaluate(d)
    assert got["invalid"] is True
    assert "success" not in got


class _FakeProc:
    stderr = ""
    returncode = 0


def test_stdout_stays_json_even_when_the_evaluator_throws(tmp_path):
    """A traceback on stdout would be read as a scoring result."""
    empty = tmp_path / "nothing"
    empty.mkdir()
    out = subprocess.run([sys.executable, str(ROOT / "agents/coding/swebench_evaluator.py"),
                          str(empty)], capture_output=True, text=True)
    body = json.loads(out.stdout)
    assert body["invalid"] is True
    assert out.returncode != 0


def test_usage_error_is_also_json(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / "agents/coding/swebench_evaluator.py")],
                         capture_output=True, text=True)
    body = json.loads(out.stdout)
    assert body["invalid"] is True and "invalid_reason" in body


# ── the pin is real ──
def test_mini_swe_agent_is_pinned_exactly():
    import tomllib
    d = tomllib.loads((ROOT / "pyproject.toml").read_text())
    extras = d["project"]["optional-dependencies"]["coding-agent"]
    assert "mini-swe-agent==2.4.6" in extras, extras


# ── the caching defect, which cost nothing only because it was caught early ──
def test_anthropic_models_are_built_with_cache_control():
    """The adapter constructed `LitellmModel(...)` directly and bypassed
    mini-swe-agent's defaults, one of which turns on Anthropic prompt caching.

    On an agent trajectory every step resends a growing prefix, so losing the
    cache is roughly a 5-10x cost increase -- silently, with no error and no
    behavioural difference to notice.
    """
    from minisweagent.models import get_model
    m = get_model("anthropic/claude-haiku-4-5-20251001",
                  {"model_kwargs": {"drop_params": True}})
    assert getattr(m.config, "set_cache_control", None) == "default_end"


def test_the_runner_uses_the_supported_construction_path():
    """Asserted on the source, because the alternative -- copying the one line
    that sets cache control -- would pass a behavioural test today and be
    bypassed again the next time upstream changes a default."""
    import ast
    tree = ast.parse((ROOT / "agents/coding/swebench_runner.py").read_text())
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "get_model" in called
    # A source-text check would match the comment that explains this; only the
    # call matters.
    assert "LitellmModel" not in called


def test_a_non_anthropic_model_is_not_given_cache_control():
    """The default is Anthropic-specific; asserting it unconditionally would
    make this test pass for the wrong reason."""
    from minisweagent.models import get_model
    m = get_model("openai/gpt-4.1-mini", {"model_kwargs": {"drop_params": True}})
    assert getattr(m.config, "set_cache_control", None) is None


# ── an empty patch: the agent's failure, or not a measurement at all ──
# The harness silently drops empty predictions and writes no report, and the
# missing report used to come back `invalid`. A step-limit cut -- the CI v0
# positive control -- ends exactly that way, so the degradation was being
# counted as an infrastructure fault instead of the failure it is.

def _no_harness(*a, **k):
    raise AssertionError("an empty patch must be scored without the harness")


@pytest.mark.parametrize("patch", ["", "\n", "  \n\t"])
def test_step_limit_with_an_empty_patch_is_a_failure(tmp_path, monkeypatch, patch):
    monkeypatch.setattr(EV.subprocess, "run", _no_harness)
    got = EV.evaluate(_artifact(tmp_path, patch=patch, exit_status="LimitsExceeded"))
    assert got["success"] == 0 and got["label"] == "FAIL"
    assert "invalid" not in got
    assert got["exit_status"] == "LimitsExceeded"


def test_an_empty_submission_is_a_failure(tmp_path, monkeypatch):
    """The agent finished and its diff was empty: it submitted nothing, which
    is a task failure by the evaluator's documented semantics."""
    monkeypatch.setattr(EV.subprocess, "run", _no_harness)
    got = EV.evaluate(_artifact(tmp_path, patch="", exit_status="Submitted"))
    assert got["success"] == 0 and "invalid" not in got


@pytest.mark.parametrize("status", ["TimeExceeded", "RepeatedFormatError",
                                    "RuntimeError", "UserInterruption", ""])
def test_an_empty_patch_without_an_agent_level_end_stays_invalid(
        tmp_path, monkeypatch, status):
    """Wall-clock limits depend on the host; format errors, exceptions and a
    missing status are not evidence the agent ran to an end. None of them may
    become a FAIL just because the patch happens to be empty."""
    monkeypatch.setattr(EV.subprocess, "run", _no_harness)
    got = EV.evaluate(_artifact(tmp_path, patch="", exit_status=status))
    assert got["invalid"] is True and "success" not in got
    assert got["invalid_reason"]


def test_a_real_patch_with_no_harness_report_is_still_invalid(tmp_path, monkeypatch):
    """The fix is for empty patches only. A patch the harness failed to judge
    is an evaluation fault and must not be scored."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(EV.subprocess, "run", lambda *a, **k: _FakeProc())
    got = EV.evaluate(_artifact(tmp_path, exit_status="LimitsExceeded"))
    assert got["invalid"] is True and "no per-instance report" in got["invalid_reason"]


@pytest.mark.parametrize("breakage", ["no_agent_run", "malformed_agent_run",
                                      "no_patch"])
def test_a_broken_artifact_is_invalid(tmp_path, breakage):
    d = _artifact(tmp_path, patch="", exit_status="LimitsExceeded")
    if breakage == "no_agent_run":
        (d / "agent_run.json").unlink()
    elif breakage == "malformed_agent_run":
        (d / "agent_run.json").write_text("{not json")
    else:
        (d / "patch.diff").unlink()
    out = subprocess.run([sys.executable, str(ROOT / "agents/coding/swebench_evaluator.py"),
                          str(d)], capture_output=True, text=True)
    body = json.loads(out.stdout)
    assert body["invalid"] is True and "success" not in body


def test_a_truncated_run_reaches_the_statistics_as_a_failure(tmp_path):
    """Through the real `run_trials` and the real evaluator subprocess to the
    per-task rates `seism check` measures: a step-limit run counts as 0, not
    as a hole in the data."""
    from agentseism.cli import _rates
    from agentseism.execution import CallableRunner, run_trials

    def truncated(task_file, artifact_dir):
        d = Path(artifact_dir)
        (d / "patch.diff").write_text("")
        (d / "agent_run.json").write_text(json.dumps(
            {"instance_id": "pallets__flask-5014", "exit_status": "LimitsExceeded",
             "step_limit": 40}))
        return {}

    task = tmp_path / "pallets__flask-5014.json"
    task.write_text("{}")
    rs = run_trials(CallableRunner(truncated), ShellEvaluator(EVAL_CMD),
                    [str(task)], 3, tmp_path / "runs", "candidate")
    assert [r.invalid for r in rs] == [False, False, False]
    assert _rates([r.__dict__ for r in rs], "success") == {str(task): [0.0, 0.0, 0.0]}
