from types import SimpleNamespace

from agentseism import run_experiment
from agentseism.alignment import align_runs
from agentseism.trace import TraceCollector
from agents.trajectory import record_trajectory, steps_from_messages


def _messages(n_iterations: int) -> list:
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]
    for i in range(n_iterations):
        messages.append(
            {
                "role": "assistant",
                "content": f"step {i}",
                "tool_calls": [{"name": "search", "args": {"q": i}, "id": f"c{i}"}],
            }
        )
        messages.append({"role": "tool", "name": "search", "content": f"result {i}"})
    return messages


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


def test_projection_records_the_core_execution_points():
    trace = TraceCollector("r0")
    summary = record_trajectory(
        trace, question="q", steps=steps_from_messages(_messages(2)), answer="Paris"
    )
    names = [e.name for e in trace.events]
    for slot in ("intake", "plan", "tool_sequence", "tool_set", "evidence", "n_steps", "final_answer"):
        assert slot in names
    assert summary["n_steps"] == 4
    assert summary["iterations_beyond_projection"] == 0


def test_projection_reports_iterations_beyond_the_window():
    trace = TraceCollector("r0")
    summary = record_trajectory(
        trace,
        question="q",
        steps=steps_from_messages(_messages(6)),
        answer="Paris",
        max_iterations=3,
    )
    assert summary["iterations_beyond_projection"] == 3
    assert trace.events[-1].output == "Paris"


def test_variable_length_trajectories_still_align_on_core_points():
    """The reason the projection exists: run length must not break alignment."""
    lengths = iter([2, 5, 3, 7])

    def agent(task_input, trace):
        steps = steps_from_messages(_messages(next(lengths)))
        record_trajectory(trace, question=task_input, steps=steps, answer="Paris")
        return "Paris"

    experiment = run_experiment(agent, ["q"], trials=4)
    slots = {s.key: s for s in align_runs(experiment.runs)}
    for slot in ("intake", "plan", "tool_sequence", "evidence", "n_steps", "final_answer"):
        assert slots[slot].coverage == 1.0

    # Length itself is recorded as behavior rather than hidden by alignment.
    assert {e.output for r in experiment.runs for e in r.events if e.name == "n_steps"} == {4, 10, 6, 14}
