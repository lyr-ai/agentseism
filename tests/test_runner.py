import pytest

from agentseism import run_experiment
from agentseism.runner import as_tasks
from agentseism.types import Task


def test_as_tasks_accepts_mixed_forms():
    tasks = as_tasks(["raw", {"id": "x", "input": 1}, Task(id="t", input=2)])
    assert [t.id for t in tasks] == ["0", "x", "t"]
    assert [t.input for t in tasks] == ["raw", 1, 2]


def test_runner_repeats_each_task():
    experiment = run_experiment(lambda x: x * 2, [1, 2], trials=3)
    assert len(experiment.runs) == 6
    assert {r.outcome for r in experiment.runs_for("0")} == {2}


def test_runner_applies_outcome_selector():
    experiment = run_experiment(
        lambda x: {"answer": x, "noise": "whatever"}, ["q"], trials=2,
        outcome=lambda r: r["answer"],
    )
    assert all(r.outcome == "q" for r in experiment.runs)


def test_runner_collects_trace():
    def agent(x, trace):
        step = trace.record("model_call", "plan", input=x, output=f"plan-{x}")
        return trace.record("decision", "decide", input=step, output="done")

    experiment = run_experiment(agent, ["a"], trials=2)
    run = experiment.runs[0]
    assert [e.name for e in run.events] == ["plan", "decide"]
    assert run.events[1].parent_ids == [run.events[0].id]


def test_runner_accepts_events_returned_directly():
    from agentseism.types import Event

    def agent(x):
        return "out", [Event(id="e", run_id="r", event_type="tool_call", name="t", output=1)]

    experiment = run_experiment(agent, ["a"], trials=1)
    assert experiment.runs[0].output == "out"
    assert experiment.runs[0].events[0].name == "t"


def test_failing_run_is_recorded_not_raised():
    def agent(x):
        raise RuntimeError("boom")

    experiment = run_experiment(agent, ["a"], trials=2)
    assert len(experiment.runs) == 2
    assert all(not r.ok for r in experiment.runs)
    assert experiment.runs_for("0") == []

    with pytest.raises(RuntimeError):
        run_experiment(agent, ["a"], trials=1, on_error="raise")


def test_runner_rejects_zero_trials():
    with pytest.raises(ValueError):
        run_experiment(lambda x: x, ["a"], trials=0)
