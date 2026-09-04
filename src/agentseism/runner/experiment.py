"""Experiment runner (DESIGN.md §10).

Runs the same agent on the same tasks under the same configuration N times and
persists every result. No perturbation: the first experiment measures natural
run-to-run variation.
"""

from __future__ import annotations

import inspect
import time
import traceback
from typing import Any, Callable, Iterable, Sequence

from agentseism.trace import TraceCollector
from agentseism.types import Experiment, Run, Task


def as_tasks(cases: Iterable[Any]) -> list[Task]:
    """Accept raw inputs, dicts, or ``Task`` objects."""
    tasks: list[Task] = []
    for i, case in enumerate(cases):
        if isinstance(case, Task):
            tasks.append(case)
        elif isinstance(case, dict) and "input" in case:
            tasks.append(
                Task(
                    id=str(case.get("id", i)),
                    input=case["input"],
                    metadata=case.get("metadata", {}),
                )
            )
        else:
            tasks.append(Task(id=str(i), input=case))
    return tasks


def _accepts_trace(agent: Callable) -> bool:
    try:
        params = inspect.signature(agent).parameters
    except (TypeError, ValueError):
        return False
    if "trace" in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def run_experiment(
    agent: Callable,
    cases: Sequence[Any],
    trials: int = 10,
    *,
    outcome: Callable[[Any], Any] | None = None,
    agent_id: str = "agent",
    experiment_id: str = "experiment",
    config: dict | None = None,
    on_error: str = "record",
) -> Experiment:
    """Execute ``agent`` on every case ``trials`` times.

    The agent may be a plain callable ``f(input) -> output``. If it accepts a
    ``trace`` keyword it is handed a :class:`TraceCollector` and its events are
    stored with the run; if it returns ``(output, events)`` those events are used
    instead. Uninstrumented agents still support outcome-level analysis
    (DESIGN.md §10) -- only event-level attribution needs a trace.
    """
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if on_error not in ("record", "raise"):
        raise ValueError("on_error must be 'record' or 'raise'")

    tasks = as_tasks(cases)
    select_outcome = outcome or (lambda result: result)
    wants_trace = _accepts_trace(agent)

    experiment = Experiment(
        id=experiment_id,
        agent_id=agent_id,
        tasks=tasks,
        config={"trials": trials, **(config or {})},
    )

    for task in tasks:
        for trial in range(trials):
            run_id = f"{task.id}:{trial}"
            collector = TraceCollector(run_id)
            started = time.perf_counter()
            output: Any = None
            error: str | None = None
            events = []
            try:
                if wants_trace:
                    output = agent(task.input, trace=collector)
                else:
                    output = agent(task.input)
                if isinstance(output, tuple) and len(output) == 2 and isinstance(output[1], list):
                    output, events = output
                else:
                    events = collector.events
            except Exception:  # noqa: BLE001 - a crashing run is data, not a bug
                if on_error == "raise":
                    raise
                error = traceback.format_exc(limit=3)
                events = collector.events
            duration_ms = (time.perf_counter() - started) * 1000

            experiment.runs.append(
                Run(
                    id=run_id,
                    task_id=task.id,
                    input=task.input,
                    output=output,
                    outcome=None if error else select_outcome(output),
                    events=events,
                    duration_ms=duration_ms,
                    error=error,
                    metadata={"trial": trial},
                )
            )

    return experiment
