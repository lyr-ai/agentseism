"""Adapter for LangGraph agents.

Wraps a compiled LangGraph app as an AgentSeism agent callable. AgentSeism does
not import langgraph or langchain: the app is duck-typed (``invoke``/``ainvoke``)
and the trajectory is read from the message list in the final state. That keeps
the adapter usable against any agent that ends up with a LangChain-style message
history, including ones already captured to disk.

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

from agents.trajectory import ReActProjector, record_raw_trace, steps_from_messages


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
    ) -> None:
        self.app = app
        self.build_state = build_state
        self.extract_answer = extract_answer
        self.extract_messages = extract_messages or _default_messages
        self.config = config or {"recursion_limit": 30}

    def __call__(self, task_input: Any, trace) -> dict:
        state = self.build_state(task_input)
        final_state = self._invoke(state)

        steps = steps_from_messages(self.extract_messages(final_state))
        answer = self.extract_answer(final_state)
        summary = record_raw_trace(
            trace, question=_question_text(task_input), steps=steps, answer=answer
        )
        return {"answer": answer, "trajectory": summary}

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


def _question_text(task_input: Any) -> Any:
    if isinstance(task_input, dict):
        return task_input.get("question", task_input)
    return task_input
