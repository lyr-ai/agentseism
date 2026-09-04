"""A synthetic multi-step agent with an injectable weak point.

This agent is not a model of any real system. It exists so that attribution can
be scored against ground truth: exactly one execution point is made stochastic
in a way that propagates to the outcome, while other points are noisy in ways
that do not. A ranker that cannot recover the injected point here has no chance
on a real agent.

Execution:

    intake -> retrieval -> phrasing -> evidence_selection
           -> hypothesis -> decision -> render

``phrasing`` and ``render`` always vary heavily and never reach the outcome:
they are the decoys that catch first-divergence and largest-diff baselines, and
they double as the negative control required by
DESIGN-FEATURE-PROJECTION.md §23 -- high local variation must not by itself
produce a high weak-point score.

Unlike a ReAct agent, this pipeline has a known topology, so its schema declares
feature order and the ranker may use a propagation term.
"""

from __future__ import annotations

import random
from itertools import count
from typing import Any, Callable

from agentseism.features import FeatureSchema, FeatureSpec, ObservationRole
from agentseism.projection import EventProjector

WEAK_POINTS = ("retrieval", "evidence_selection", "hypothesis", "decision")
DECOYS = ("phrasing", "render")

SCHEMA_VERSION = "synthetic/1"

SCHEMA = FeatureSchema(
    version=SCHEMA_VERSION,
    specs=[
        FeatureSpec("intake", order=0),
        FeatureSpec("retrieval", order=1),
        FeatureSpec("phrasing", order=2, description="decoy: varies always, reaches nothing"),
        FeatureSpec("evidence_selection", order=3),
        FeatureSpec("hypothesis", order=4),
        FeatureSpec("decision", order=5),
        FeatureSpec("render", order=6, description="decoy: terminal prose"),
        FeatureSpec("submitted_answer", role=ObservationRole.OUTCOME),
    ],
)


def projector() -> EventProjector:
    """Named execution points project directly onto the declared schema."""
    return EventProjector(SCHEMA)

_WORDS = [
    "considering", "the", "evidence", "suggests", "a", "possible",
    "underlying", "cause", "given", "observed", "signals", "however",
]


def _prose(rng: random.Random, n: int = 8) -> str:
    return " ".join(rng.choice(_WORDS) for _ in range(n))


def make_synthetic_agent(
    weak_point: str = "evidence_selection",
    *,
    seed: int = 0,
    flip_prob: float = 0.5,
) -> Callable[..., Any]:
    """Build an agent whose only consequential stochasticity is at ``weak_point``.

    ``flip_prob`` controls how often that point takes its alternative branch.
    """
    if weak_point not in WEAK_POINTS:
        raise ValueError(f"weak_point must be one of {WEAK_POINTS}")

    counter = count()

    def agent(task_input: Any, trace) -> dict:
        rng = random.Random(f"{seed}:{next(counter)}")
        unstable = lambda point: point == weak_point and rng.random() < flip_prob  # noqa: E731

        topic = trace.record(
            "transform", "intake", input=task_input, output=str(task_input).strip().lower()
        )

        docs = [f"{topic}-doc-a", f"{topic}-doc-b"]
        if unstable("retrieval"):
            docs = list(reversed(docs))
        docs = trace.record("retrieval", "retrieval", input=topic, output=docs)

        trace.record("model_call", "phrasing", input=topic, output=_prose(rng))

        index = 1 if unstable("evidence_selection") else 0
        evidence = trace.record(
            "decision", "evidence_selection", input=docs, output=docs[index]
        )

        hypothesis = f"cause-of-{evidence}"
        if unstable("hypothesis"):
            hypothesis = f"secondary-driver-of-{evidence}"
        hypothesis = trace.record(
            "model_call", "hypothesis", input=evidence, output=hypothesis
        )

        answer = f"answer::{hypothesis}"
        if unstable("decision"):
            answer = "answer::insufficient-evidence"
        answer = trace.record("decision", "decision", input=hypothesis, output=answer)

        note = trace.record("model_call", "render", input=answer, output=_prose(rng, 12))
        trace.record("final_submission", "submitted_answer", output=answer)

        return {"answer": answer, "note": note}

    agent.__name__ = f"synthetic_agent[{weak_point}]"
    return agent


def outcome(result: dict) -> str:
    """The behavior we care about: the answer, not its prose."""
    return result["answer"]
