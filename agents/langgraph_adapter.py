"""Adapter for LangGraph agents.

Wraps a compiled LangGraph app as an AgentSeism agent callable. AgentSeism does
not import langgraph or langchain: the app is duck-typed and the trajectory is
read from LangChain-style messages.

Two capture modes, and the choice is not cosmetic:

``stream`` (default when the app supports it)
    Records each node's state delta as it is produced. Required for any agent
    whose graph *rewrites its own history* -- a context-trimming node that
    replaces old tool results with a placeholder destroys the evidence a later
    reader would need, so the trajectory has to be captured as it happens.

``invoke``
    Runs the graph and reads the final message list. Fine for agents that only
    append to their history.

    from agents.langgraph_adapter import LangGraphAgent
    from agents.gaia import build_state, extract_answer

    agent = LangGraphAgent(app, build_state=build_state, extract_answer=extract_answer)
    report = scan(agent, cases=tasks, trials=5, outcome=lambda r: r["answer"],
                  projector=ReActProjector())
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

__all__ = ["LangGraphAgent", "ReActProjector"]

from agents.trajectory import (
    ReActProjector,
    record_graph_stream,
    record_raw_trace,
    steps_from_messages,
)


class LangGraphAgent:
    """An AgentSeism agent callable backed by a compiled LangGraph app."""

    def __init__(
        self,
        app: Any,
        *,
        build_state: Callable[[Any], Any],
        extract_answer: Callable[[Any], Any],
        extract_messages: Callable[[Any], list] | None = None,
        config: dict | None = None,
        capture: str = "auto",
    ) -> None:
        self.app = app
        self.build_state = build_state
        self.extract_answer = extract_answer
        self.extract_messages = extract_messages or _default_messages
        self.config = config or {"recursion_limit": 30}
        if capture not in ("auto", "stream", "invoke"):
            raise ValueError("capture must be 'auto', 'stream', or 'invoke'")
        self.capture = capture

    def __call__(self, task_input: Any, trace) -> dict:
        state = self.build_state(task_input)
        question = _question_text(task_input)

        if self._streams():
            updates = list(self.app.stream(state, self.config, stream_mode="updates"))
            summary = record_graph_stream(trace, question=question, updates=updates)
            answer = self.extract_answer(_state_from_updates(state, updates))
            trace.record("final_submission", "final_submission", output=answer)
            return {"answer": answer, "trajectory": summary}

        final_state = self._invoke(state)
        steps = steps_from_messages(self.extract_messages(final_state))
        answer = self.extract_answer(final_state)
        summary = record_raw_trace(
            trace, question=question, steps=steps, answer=answer
        )
        return {"answer": answer, "trajectory": summary}

    def _streams(self) -> bool:
        if self.capture == "invoke":
            return False
        has_stream = callable(getattr(self.app, "stream", None))
        if self.capture == "stream" and not has_stream:
            raise TypeError("capture='stream' but the app has no stream()")
        return has_stream

    def _invoke(self, state: Any) -> Any:
        invoke = getattr(self.app, "invoke", None)
        if invoke is not None and not inspect.iscoroutinefunction(invoke):
            result = invoke(state, self.config)
            return asyncio.run(result) if inspect.isawaitable(result) else result
        ainvoke = getattr(self.app, "ainvoke", None) or invoke
        if ainvoke is None:
            raise TypeError("app must provide invoke() or ainvoke()")
        return asyncio.run(ainvoke(state, self.config))


def _default_messages(final_state: Any) -> list:
    if isinstance(final_state, dict):
        return final_state.get("messages", [])
    return getattr(final_state, "messages", [])


def _state_from_updates(initial: Any, updates: list) -> dict:
    """Rebuild an approximate final state from streamed node deltas.

    Only used to hand something to ``extract_answer``; the trajectory itself
    comes from the deltas, which is the point of streaming.
    """
    state = dict(initial) if isinstance(initial, dict) else {"messages": []}
    messages = list(state.get("messages", []))
    for update in updates:
        for delta in (update or {}).values():
            if isinstance(delta, dict):
                messages.extend(delta.get("messages", []) or [])
                for key, value in delta.items():
                    if key != "messages":
                        state[key] = value
    state["messages"] = messages
    return state


def _question_text(task_input: Any) -> Any:
    if isinstance(task_input, dict):
        return task_input.get("question", task_input)
    return task_input
