"""A stub ReAct app with a LangGraph-shaped interface.

Not an experiment subject: this exists so the GAIA pipeline -- adapter,
trajectory projection, alignment, report -- can be exercised without API keys,
and so the tests cover variable-length trajectories, which are the case that
occurrence-index alignment gets wrong.

It mimics the message shape of the reference GAIA agent: assistant messages
carrying tool calls, tool messages carrying results, and a final assistant
message that submits an answer.
"""

from __future__ import annotations

import random
from itertools import count
from typing import Any

TOOLS = ["tavily_search", "sum_array"]


class StubReActApp:
    """``invoke(state, config) -> final_state`` with run-to-run variation.

    ``branch_prob`` controls how often the agent picks the second tool for its
    first call -- the consequential choice. ``detour_prob`` controls how often it
    takes an extra, inconsequential iteration, which changes trajectory length
    without changing the answer.
    """

    def __init__(self, *, seed: int = 0, branch_prob: float = 0.4, detour_prob: float = 0.5) -> None:
        self.seed = seed
        self.branch_prob = branch_prob
        self.detour_prob = detour_prob
        self._counter = count()

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        rng = random.Random(f"{self.seed}:{next(self._counter)}")
        question = state["question"]
        question_text = question["question"] if isinstance(question, dict) else str(question)

        branch = 1 if rng.random() < self.branch_prob else 0
        tool = TOOLS[branch]
        messages: list[dict[str, Any]] = list(state.get("messages", []))

        messages.append(
            {
                "role": "assistant",
                "content": f"Thinking about {question_text[:20]} {rng.random():.3f}",
                "tool_calls": [{"name": tool, "args": {"query": question_text}, "id": "c0"}],
            }
        )
        evidence = f"evidence-from-{tool}"
        messages.append({"role": "tool", "name": tool, "content": evidence})

        # An inconsequential detour: extra iteration, same evidence, same answer.
        if rng.random() < self.detour_prob:
            messages.append(
                {
                    "role": "assistant",
                    "content": "Double-checking.",
                    "tool_calls": [{"name": "tavily_search", "args": {"query": "recheck"}, "id": "c1"}],
                }
            )
            messages.append({"role": "tool", "name": "tavily_search", "content": evidence})

        answer = f"answer-{branch}"
        messages.append(
            {
                "role": "assistant",
                "content": f"Submitting. {rng.random():.3f}",
                "tool_calls": [
                    {"name": "submit_final_answer", "args": {"answer": answer}, "id": "cf"}
                ],
            }
        )
        messages.append(
            {"role": "tool", "name": "submit_final_answer", "content": "submitted"}
        )

        return {
            "question": question,
            "final_agent_answer": {"task_id": _task_id(question), "agent_answer": answer},
            "messages": messages,
        }


def _task_id(question: Any) -> Any:
    return question.get("task_id") if isinstance(question, dict) else None
