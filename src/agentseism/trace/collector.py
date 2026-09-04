"""Trace collection.

Instrumentation is optional and deliberately minimal: the agent records the
execution points it already has, with a stable ``name`` per point. AgentSeism is
not a tracing backend (DESIGN.md §5) -- this exists only so that runs can be
aligned and compared event by event.

    def agent(task_input, trace):
        docs = trace.record("retrieval", "retrieve", input=task_input, output=search(task_input))
        ...
"""

from __future__ import annotations

from typing import Any

from agentseism.types import Event


class TraceCollector:
    """Collects the events of a single run, in execution order."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.events: list[Event] = []

    def record(
        self,
        event_type: str,
        name: str | None = None,
        *,
        input: Any = None,
        output: Any = None,
        parent_ids: list[str] | None = None,
        **metadata: Any,
    ) -> Any:
        """Record one execution point and return ``output`` unchanged.

        Returning the output keeps instrumentation inline-able:
        ``plan = trace.record("model_call", "plan", output=llm(prompt))``.
        """
        event = Event(
            id=f"{self.run_id}:{len(self.events)}",
            run_id=self.run_id,
            event_type=event_type,
            name=name,
            input=input,
            output=output,
            parent_ids=parent_ids if parent_ids is not None else self._default_parents(),
            metadata=metadata,
        )
        self.events.append(event)
        return output

    def _default_parents(self) -> list[str]:
        return [self.events[-1].id] if self.events else []
