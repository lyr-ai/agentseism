from types import SimpleNamespace

from agents.trajectory import ReActProjector, record_raw_trace, steps_from_messages
from agentseism import run_experiment
from agentseism.alignment import align_features
from agentseism.trace import TraceCollector
from agentseism.types import Run


def _messages(n_iterations: int, tool: str = "search") -> list:
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]
    for i in range(n_iterations):
        messages.append(
            {
                "role": "assistant",
                "content": f"step {i}",
                "tool_calls": [{"name": tool, "args": {"q": i}, "id": f"c{i}"}],
            }
        )
        messages.append({"role": "tool", "name": tool, "content": f"result {i}"})
    return messages


def _project(n_iterations: int, tool: str = "search") -> dict:
    trace = TraceCollector("r")
    record_raw_trace(
        trace, question="q", steps=steps_from_messages(_messages(n_iterations, tool)), answer="Paris"
    )
    run = Run(id="r", task_id="t", input="q", output=None, outcome="Paris", events=trace.events)
    return ReActProjector().project(run)


def test_steps_from_dict_messages():
    steps = steps_from_messages(_messages(2))
    assert [s.kind for s in steps] == ["model", "tool", "model", "tool"]
    assert steps[0].tool_name == "search"
    assert steps[1].content == "result 0"


def test_steps_from_object_messages_and_block_content():
    messages = [
        SimpleNamespace(
            type="ai",
            content=[{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}],
            tool_calls=[{"name": "calc", "args": {}}],
        ),
        SimpleNamespace(type="tool", name="calc", content="7"),
        SimpleNamespace(type="human", content="ignored"),
    ]
    steps = steps_from_messages(messages)
    assert [s.kind for s in steps] == ["model", "tool"]
    assert steps[0].content == "hello world"
    assert steps[0].tool_name == "calc"


def test_raw_trace_keeps_every_step():
    """The raw trace is not truncated; only the projection is a summary."""
    trace = TraceCollector("r")
    record_raw_trace(trace, question="q", steps=steps_from_messages(_messages(7)), answer="Paris")
    assert sum(1 for e in trace.events if e.name == "model_call") == 7
    assert sum(1 for e in trace.events if e.name == "tool_call") == 7
    assert trace.events[-1].name == "final_submission"


def test_projection_produces_the_declared_schema():
    features = _project(3)
    assert set(features) == {s.name for s in ReActProjector.schema.specs}
    assert features["tool_call_count"] == 3
    assert features["tool_set"] == ["search"]
    assert features["initial_plan"] == "step 0"
    assert features["final_answer"] == "Paris"


def test_loop_length_is_behavior_not_missing_data():
    """A longer run differs in count and sequence, but stays comparable."""
    short, long = _project(2), _project(5)
    assert short["tool_set"] == long["tool_set"]
    assert short["tool_call_count"] != long["tool_call_count"]
    assert short["tool_sequence"] != long["tool_sequence"]


def test_tool_set_separates_capability_choice_from_path_length():
    same_tools = _project(4, tool="search")
    other_tool = _project(4, tool="calculator")
    assert same_tools["tool_set"] != other_tool["tool_set"]

    longer_same_tool = _project(6, tool="search")
    assert same_tools["tool_set"] == longer_same_tool["tool_set"]


def test_variable_length_trajectories_align_on_every_feature():
    """The reason projection exists: run length must not break alignment."""
    lengths = iter([2, 5, 3, 7])

    def agent(task_input, trace):
        steps = steps_from_messages(_messages(next(lengths)))
        record_raw_trace(trace, question=task_input, steps=steps, answer="Paris")
        return "Paris"

    experiment = run_experiment(agent, ["q"], trials=4, projector=ReActProjector())
    columns = {c.name: c for c in align_features(experiment.runs, experiment.schema)}
    for name in ("tool_set", "tool_sequence", "tool_call_count", "evidence_set", "initial_plan"):
        assert columns[name].coverage == 1.0
    assert set(columns["tool_call_count"].values.values()) == {2, 5, 3, 7}
