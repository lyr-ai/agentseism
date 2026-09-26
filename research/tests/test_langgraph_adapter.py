import pytest

from agents.gaia import answer_equivalent, build_state, extract_answer, outcome
from agents.langgraph_adapter import LangGraphAgent
from agents.stub_react import StubReActApp
from agents.trajectory import ReActProjector
from agentseism import scan
from agentseism.runner.experiment import TraceCollector

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
    # The stub's only consequential choice is which tool it calls first: among
    # the aggregates that is the tool set, among positioned features the
    # evidence it produced.
    assert report.ranking.aggregates[0].name in ("tool_set", "tool_sequence")
    assert report.ranking.positioned[0].name == "evidence_set"
    # Loop length varies without changing the answer, so it must not lead.
    assert ranked["tool_call_count"].score < ranked["tool_set"].score
    # Prose before submission is the negative control.
    assert ranked["pre_final_reasoning"].score < ranked["evidence_set"].score


def test_partial_order_splits_positioned_features_from_aggregates():
    report = _scan()
    ranking = report.ranking
    assert ranking.mixed
    assert [w.name for w in ranking.positioned] != []
    assert {w.name for w in ranking.aggregates} == {
        "tool_set", "tool_sequence", "tool_call_count"
    }
    assert all(w.propagation is not None for w in ranking.positioned)
    assert all(w.propagation is None for w in ranking.aggregates)

    text = report.render()
    assert "Positioned execution features   (score = V x A x P)" in text
    assert "Trajectory aggregates   (score = V x A)" in text
    assert "N/A (trajectory aggregate)" in text
    assert "not across them" in text


def test_outcome_observation_is_excluded_and_reported():
    report = _scan()
    assert "final_answer" not in {w.name for w in report.weak_points}
    assert "Excluded from attribution: final_answer" in report.render()
    assert "Feature schema: react/1" in report.render()


def test_deterministic_app_shows_no_variation():
    report = _scan(StubReActApp(branch_prob=0.0, detour_prob=0.0), trials=4)
    assert report.consistency == 1.0
    assert all(w.score == 0.0 for w in report.weak_points)


# --- async-only graphs (open_deep_research shape) ----------------------------

class _AsyncOnlyApp:
    """A graph whose nodes are async: stream() exists but raises from inside.

    This is the shape langgraph produces for an async-only graph, and it is why
    the adapter cannot decide on `hasattr(app, "stream")` alone.
    """

    def __init__(self, updates):
        self._updates = updates

    def stream(self, state, config=None, stream_mode="updates"):
        raise TypeError('No synchronous function provided to "node_a".')

    async def astream(self, state, config=None, stream_mode="updates"):
        for update in self._updates:
            yield update


def test_async_only_graph_is_captured_by_streaming():
    updates = [
        {"node_a": {"messages": [{"role": "assistant", "content": "a"}]}},
        {"node_b": {"messages": [{"role": "assistant", "content": "b"}]}},
    ]
    agent = LangGraphAgent(
        _AsyncOnlyApp(updates),
        build_state=lambda x: {"messages": []},
        extract_answer=lambda s: "done",
    )
    collector = TraceCollector("async:0")
    out = agent({"question": "q"}, trace=collector)
    assert out["answer"] == "done"
    assert {e.name for e in collector.events} >= {"node_a", "node_b"}


def test_sync_type_errors_that_are_not_about_async_still_raise():
    class Broken(_AsyncOnlyApp):
        def stream(self, state, config=None, stream_mode="updates"):
            raise TypeError("build_state returned the wrong shape")

    agent = LangGraphAgent(
        Broken([]),
        build_state=lambda x: {"messages": []},
        extract_answer=lambda s: "done",
    )
    with pytest.raises(TypeError, match="wrong shape"):
        agent({"question": "q"}, trace=TraceCollector("async:1"))
