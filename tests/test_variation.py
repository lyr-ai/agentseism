from agentseism import EventProjector, run_experiment
from agentseism.alignment import align_features
from agentseism.features import MISSING, FeatureSchema, FeatureSpec
from agentseism.variation import consistency, feature_divergences, outcome_modes, task_variation


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


def test_repeated_event_names_project_to_occurrence_suffixed_features():
    def agent(x, trace):
        trace.record("tool_call", "search", output="a")
        trace.record("tool_call", "search", output="b")
        trace.record("decision", "decide", output="d")
        return "out"

    experiment = run_experiment(agent, ["q"], trials=2)
    columns = {c.name: c for c in align_features(experiment.runs, experiment.schema)}
    assert set(columns) == {"search", "search#1", "decide"}
    assert all(c.coverage == 1.0 for c in columns.values())


def test_missing_feature_is_maximal_divergence():
    calls = {"n": 0}

    def agent(x, trace):
        calls["n"] += 1
        trace.record("transform", "start", output="s")
        if calls["n"] % 2 == 0:
            trace.record("tool_call", "extra_lookup", output="e")
        trace.record("decision", "decide", output="d")
        return "out"

    experiment = run_experiment(agent, ["q"], trials=2)
    columns, pairs = feature_divergences(
        experiment.runs, experiment.schema, outcome_comparator="exact"
    )
    extra = next(c for c in columns if c.name == "extra_lookup")
    assert extra.coverage == 0.5
    assert MISSING in extra.values.values()
    assert pairs[0].features["extra_lookup"] == 1.0
    assert pairs[0].features["start"] == 0.0


def test_declared_comparator_is_used_over_the_inferred_one():
    schema = FeatureSchema(
        version="t/1",
        specs=[FeatureSpec("tools", comparator="set"), FeatureSpec("step", comparator="numeric")],
    )
    calls = {"n": 0}

    def agent(x, trace):
        calls["n"] += 1
        # Same tools, different order: a set comparator must call these equal.
        trace.record("transform", "tools", output=["a", "b"] if calls["n"] % 2 else ["b", "a"])
        trace.record("transform", "step", output=10 if calls["n"] % 2 else 11)
        return "out"

    experiment = run_experiment(agent, ["q"], trials=2, projector=EventProjector(schema))
    _, pairs = feature_divergences(experiment.runs, schema, outcome_comparator="exact")
    assert pairs[0].features["tools"] == 0.0
    assert 0 < pairs[0].features["step"] < 0.2
