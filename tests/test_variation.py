from agentseism import run_experiment
from agentseism.alignment import align_runs
from agentseism.variation import consistency, outcome_modes, pair_divergences, task_variation


def test_identical_outcomes_are_fully_consistent():
    assert consistency(["a", "a", "a"], "exact") == 1.0
    assert consistency(["a"], "exact") == 1.0


def test_variation_is_one_minus_consistency():
    experiment = run_experiment(lambda x: x, ["q"], trials=4)
    tv = task_variation(experiment, "0", "exact")
    assert tv.consistency == 1.0
    assert tv.variation == 0.0
    assert len(tv.modes) == 1
    assert tv.modes[0].share == 1.0


def test_outcome_modes_report_shares():
    modes = outcome_modes(["a", "a", "a", "b", "b", "c"], "exact")
    assert [m.count for m in modes] == [3, 2, 1]
    assert modes[0].share == 0.5
    assert modes[0].run_ids == ["0", "1", "2"]


def test_task_variation_counts_errors():
    calls = {"n": 0}

    def agent(x):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return "ok"

    experiment = run_experiment(agent, ["q"], trials=3)
    tv = task_variation(experiment, "0", "exact")
    assert tv.n_runs == 2
    assert tv.n_errors == 1


def test_alignment_matches_by_name_and_occurrence():
    def agent(x, trace):
        trace.record("tool_call", "search", output="a")
        trace.record("tool_call", "search", output="b")
        trace.record("decision", "decide", output="d")
        return "out"

    experiment = run_experiment(agent, ["q"], trials=2)
    slots = align_runs(experiment.runs)
    assert [s.key for s in slots] == ["search", "search#1", "decide"]
    assert all(s.coverage == 1.0 for s in slots)


def test_missing_execution_point_is_maximal_divergence():
    calls = {"n": 0}

    def agent(x, trace):
        calls["n"] += 1
        trace.record("transform", "start", output="s")
        if calls["n"] % 2 == 0:
            trace.record("tool_call", "extra_lookup", output="e")
        trace.record("decision", "decide", output="d")
        return "out"

    experiment = run_experiment(agent, ["q"], trials=2)
    slots, pairs = pair_divergences(experiment.runs, outcome_comparator="exact")
    extra = next(s for s in slots if s.key == "extra_lookup")
    assert extra.coverage == 0.5
    assert pairs[0].slots["extra_lookup"] == 1.0
    assert pairs[0].slots["start"] == 0.0
