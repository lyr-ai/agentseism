from agentseism import scan
from agents.gaia import answer_equivalent, build_state, extract_answer, outcome
from agents.langgraph_adapter import LangGraphAgent
from agents.stub_react import StubReActApp
from agents.trajectory import ReActProjector

CASES = [
    {"id": f"stub-{i}", "input": {"task_id": f"stub-{i}", "question": f"q{i}", "file_name": ""}}
    for i in range(3)
]


def _agent(app=None):
    return LangGraphAgent(
        app or StubReActApp(),
        build_state=build_state,
        extract_answer=extract_answer,
    )


def _scan(app=None, trials=6, **kwargs):
    return scan(
        _agent(app),
        CASES,
        trials=trials,
        outcome=outcome,
        comparator=answer_equivalent,
        projector=ReActProjector(),
        **kwargs,
    )


def test_adapter_returns_answer_and_trajectory_summary():
    class Trace:
        def __init__(self):
            self.names = []

        def record(self, event_type, name=None, **kwargs):
            self.names.append(name)
            return kwargs.get("output")

    trace = Trace()
    result = _agent()(CASES[0]["input"], trace)
    assert result["answer"].startswith("answer-")
    assert result["trajectory"]["n_steps"] >= 4
    assert trace.names[0] == "intake"
    assert trace.names[-1] == "final_submission"


def test_adapter_supports_async_apps():
    class AsyncApp:
        def __init__(self):
            self.inner = StubReActApp()

        async def ainvoke(self, state, config=None):
            return self.inner.invoke(state, config)

    report = _scan(AsyncApp(), trials=2)
    assert all(r.ok for r in report.experiment.runs)
    assert all(r.features for r in report.experiment.runs)


def test_scan_over_stub_agent_localizes_weak_points():
    report = _scan(agent_id="stub-react")
    assert all(r.ok for r in report.experiment.runs)
    assert report.consistency < 1.0

    ranked = {w.name: w for w in report.weak_points}
    # The stub's only consequential choice is which tool it calls first, which
    # shows up as the tool set and the evidence it produced.
    assert report.weak_points[0].name in ("tool_set", "evidence_set")
    # Loop length varies without changing the answer, so it must not lead.
    assert ranked["tool_call_count"].score < ranked["tool_set"].score
    # Prose before submission is the negative control.
    assert ranked["pre_final_reasoning"].score < ranked["tool_set"].score


def test_unordered_schema_reports_no_propagation_term():
    report = _scan()
    assert report.ranking.scoring_mode == "V x A"
    assert all(w.propagation is None for w in report.weak_points)
    assert "score = V x A" in report.render()


def test_outcome_observation_is_excluded_and_reported():
    report = _scan()
    assert "final_answer" not in {w.name for w in report.weak_points}
    assert "Excluded from attribution: final_answer" in report.render()
    assert "Feature schema: react/1" in report.render()


def test_deterministic_app_shows_no_variation():
    report = _scan(StubReActApp(branch_prob=0.0, detour_prob=0.0), trials=4)
    assert report.consistency == 1.0
    assert all(w.score == 0.0 for w in report.weak_points)
