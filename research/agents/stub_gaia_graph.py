"""A stub of the MarkAZhang/gaia-agent graph, including its history rewriting.

Exists so the adapter, the projection and the pilot can be exercised without API
keys -- and so the `memory_management` trap stays covered by a test: this stub
overwrites earlier tool results with "removed" exactly as that graph does, so a
final-state reader would see almost no evidence while a stream reader sees all
of it.

Not an experiment subject.
"""

from __future__ import annotations

import random
from itertools import count
from typing import Any

TOOLS = ["web_search", "execute_code_snippet", "parse_document"]
TRIMMED = "removed"


class StubGaiaGraphApp:
    """``stream(state, config, stream_mode="updates")`` over the same node names.

    ``branch_prob`` picks a different first tool (the consequential choice),
    ``detour_prob`` adds an inconsequential extra loop, ``retry_prob`` makes the
    agent emit a badly formatted answer once so the check node loops back,
    ``refusal_prob`` ends the run at the refusal node, and
    ``formatter_error_prob`` makes the output formatter return a *different*
    answer -- variation introduced downstream of the agent.
    """

    def __init__(
        self,
        *,
        seed: int = 0,
        branch_prob: float = 0.4,
        detour_prob: float = 0.5,
        retry_prob: float = 0.2,
        refusal_prob: float = 0.0,
        formatter_error_prob: float = 0.0,
    ) -> None:
        self.seed = seed
        self.branch_prob = branch_prob
        self.detour_prob = detour_prob
        self.retry_prob = retry_prob
        self.refusal_prob = refusal_prob
        self.formatter_error_prob = formatter_error_prob
        self._counter = count()

    def stream(self, state: dict, config: dict | None = None, stream_mode: str = "updates"):
        if stream_mode != "updates":
            raise ValueError("this stub only streams 'updates'")
        rng = random.Random(f"{self.seed}:{next(self._counter)}")
        question = _question(state)
        branch = 1 if rng.random() < self.branch_prob else 0
        tool = TOOLS[branch]
        answer = f"answer-{branch}"
        trimmed_so_far = 0

        yield {"core_agent": {"messages": [_ai(f"Plan for {question[:16]} {rng.random():.3f}", tool)]}}
        yield {"tools": {"messages": [_tool(tool, f"evidence-from-{tool}")]}}
        yield {"memory_management": {"messages": []}}

        if rng.random() < self.refusal_prob:
            yield {"return_llm_refusal": {"messages": [_ai("I cannot help with that.")]}}
            return

        if rng.random() < self.detour_prob:
            extra = "web_search"
            yield {"core_agent": {"messages": [_ai("Double-checking.", extra)]}}
            yield {"tools": {"messages": [_tool(extra, "evidence-from-recheck")]}}
            # memory_management overwrites the *earlier* tool result.
            trimmed_so_far += 1
            yield {"memory_management": {"messages": [_tool(tool, TRIMMED)]}}

        if rng.random() < self.retry_prob:
            yield {"core_agent": {"messages": [_ai(f"I think it is {answer}")]}}
            yield {"check_and_get_final_answer": {"messages": [_system("Format your answer as 'Ans: ...'")]}}

        yield {"core_agent": {"messages": [_ai(f"Reasoning {rng.random():.3f}\nAns: {answer}")]}}
        yield {"check_and_get_final_answer": {"messages": [_ai(answer)]}}
        formatted = answer.replace("-", " ")
        if rng.random() < self.formatter_error_prob:
            formatted = "unknown"
        yield {"output_formatter": {"messages": [_ai(formatted)]}}

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        """Final state only -- with the trimming applied, as the real graph does."""
        messages = list(state.get("messages", []))
        seen_tool = False
        for update in self.stream(state, config):
            for delta in update.values():
                messages.extend(delta.get("messages", []))
        # Emulate the lossy history: earlier tool results read as "removed".
        for message in messages[:-1]:
            if message.get("role") == "tool":
                if seen_tool:
                    message["content"] = TRIMMED
                seen_tool = True
        return {"messages": messages}


def _question(state: dict) -> str:
    for message in state.get("messages", []):
        if message.get("role") in ("user", "human"):
            return str(message.get("content", ""))
    return ""


def _ai(content: str, tool: str | None = None) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool:
        message["tool_calls"] = [{"name": tool, "args": {"query": content[:20]}, "id": tool}]
    return message


def _tool(name: str, content: str) -> dict:
    return {"role": "tool", "name": name, "content": content}


def _system(content: str) -> dict:
    return {"role": "system", "content": content}
