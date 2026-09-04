from agentseism import scan
from agents.gaia import answer_equivalent, build_state, extract_answer, outcome
from agents.langgraph_adapter import LangGraphAgent
from agents.stub_react import StubReActApp
from agents.trajectory import OUTCOME_SLOT

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
    assert result["trajectory"]["n_model_steps"] >= 2
    assert "final_answer" in trace.names


def test_adapter_supports_async_apps():
    class AsyncApp:
        def __init__(self):
            self.inner = StubReActApp()

        async def ainvoke(self, state, config=None):
            return self.inner.invoke(state, config)

    report = scan(_agent(AsyncApp()), CASES, trials=2, outcome=outcome, comparator=answer_equivalent)
    assert all(r.ok for r in report.experiment.runs)


def test_scan_over_stub_agent_produces_weak_points():
    report = scan(
        _agent(),
        CASES,
        trials=6,
        outcome=outcome,
        comparator=answer_equivalent,
        agent_id="stub-react",
        exclude_slots=(OUTCOME_SLOT,),
    )
    assert all(r.ok for r in report.experiment.runs)
    assert report.consistency < 1.0

    ranked = {w.label: w for w in report.weak_points}
    # The stub's only consequential choice is which tool it calls first.
    assert report.weak_points[0].label in ("tool_set", "tool_selection")
    # Trajectory length varies without changing the answer, so it must not
    # outrank the tool choice.
    assert ranked["n_steps"].score < ranked["tool_set"].score


def test_outcome_slot_is_excluded_from_ranking_but_reported():
    report = scan(
        _agent(), CASES, trials=6, outcome=outcome, comparator=answer_equivalent,
        exclude_slots=(OUTCOME_SLOT,),
    )
    assert OUTCOME_SLOT not in {w.label for w in report.weak_points}
    assert "Excluded from ranking: final_answer" in report.render()

    # Without the exclusion it would trivially rank first: it is the outcome.
    unfiltered = scan(_agent(), CASES, trials=6, outcome=outcome, comparator=answer_equivalent)
    assert unfiltered.weak_points[0].label == OUTCOME_SLOT


def test_deterministic_app_shows_no_variation():
    app = StubReActApp(branch_prob=0.0, detour_prob=0.0)
    report = scan(_agent(app), CASES, trials=4, outcome=outcome, comparator=answer_equivalent)
    assert report.consistency == 1.0
    assert all(w.score == 0.0 for w in report.weak_points)
