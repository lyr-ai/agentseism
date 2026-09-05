from agents.synthetic import SCHEMA, make_synthetic_agent, outcome, projector
from agentseism import analyze, scan
from agentseism.types import Experiment


def test_scan_without_trace_reports_outcome_variation_only():
    flip = {"n": 0}

    def agent(x):
        flip["n"] += 1
        return "a" if flip["n"] % 2 else "b"

    report = scan(agent, ["q"], trials=6, comparator="exact")
    assert report.consistency < 1.0
    assert report.weak_points == []
    assert "No trace recorded" in report.render()


def test_scan_reports_stable_agent_as_consistent():
    report = scan(lambda x: {"answer": x}, ["a", "b"], trials=5, comparator="exact")
    assert report.consistency == 1.0
    assert report.unstable_tasks == []


def test_scan_end_to_end_ranks_weak_point_and_renders():
    report = scan(
        make_synthetic_agent("evidence_selection"),
        ["latency spike", "checkout errors"],
        trials=8,
        outcome=outcome,
        comparator="exact",
        projector=projector(),
        agent_id="synthetic",
    )
    assert report.top_weak_points(1)[0].name == "evidence_selection"

    text = report.render()
    assert "AgentSeism" in text
    assert "synthetic" in text
    assert "evidence_selection" in text
    assert "Localization, not causal attribution" in text


def test_scan_persists_experiment_and_analyze_reproduces_it(tmp_path):
    path = str(tmp_path / "exp.json")
    report = scan(
        make_synthetic_agent("hypothesis"),
        ["latency spike"],
        trials=6,
        outcome=outcome,
        comparator="exact",
        projector=projector(),
        save_to=path,
    )
    reloaded = analyze(Experiment.load(path), comparator="exact")
    assert reloaded.weak_points[0].name == report.weak_points[0].name
    assert reloaded.schema.version == SCHEMA.version
    # The schema round-trips, so the scoring mode survives persistence.
    assert reloaded.ranking.scoring_mode == report.ranking.scoring_mode
    assert [w.name for w in reloaded.ranking.positioned] == [
        w.name for w in report.ranking.positioned
    ]


def test_single_trial_scan_is_well_defined():
    report = scan(lambda x: x, ["a"], trials=1, comparator="exact")
    assert report.consistency == 1.0
    assert report.weak_points == []
