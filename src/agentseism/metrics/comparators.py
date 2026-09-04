"""Outcome comparators.

A comparator is any callable ``compare(a, b) -> float`` where ``1.0`` means
behaviorally equivalent and ``0.0`` maximally different (DESIGN.md §9).

This is deliberately a small set. AgentSeism does not judge correctness, so it
does not need an evaluator library; users who want semantic judgement pass their
own comparator.
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable

Comparator = Callable[[Any, Any], float]

_TOKEN = re.compile(r"\w+")


def exact(a: Any, b: Any) -> float:
    """1.0 iff the two values are equal."""
    return 1.0 if a == b else 0.0


def jaccard(a: Any, b: Any) -> float:
    """Token-overlap similarity for free text.

    A cheap stand-in for semantic similarity. Swap in an embedding comparator
    when the outcome space needs one -- the interface is the same.
    """
    ta = set(_TOKEN.findall(str(a).lower()))
    tb = set(_TOKEN.findall(str(b).lower()))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def numeric(a: Any, b: Any, scale: float | None = None) -> float:
    """Bounded distance between two numbers."""
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return exact(a, b)
    if math.isclose(fa, fb):
        return 1.0
    denom = scale if scale else max(abs(fa), abs(fb), 1.0)
    return max(0.0, 1.0 - abs(fa - fb) / denom)


def structured(a: Any, b: Any) -> float:
    """Recursive comparison of dicts / lists / scalars.

    Dicts compare field-by-field over the union of keys; lists compare
    position-by-position, penalising length mismatch; scalars fall through to
    the scalar rules (numbers by distance, strings by token overlap).
    """
    if isinstance(a, dict) and isinstance(b, dict):
        keys = set(a) | set(b)
        if not keys:
            return 1.0
        return sum(structured(a.get(k), b.get(k)) for k in keys) / len(keys)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        n = max(len(a), len(b))
        if n == 0:
            return 1.0
        pairs = sum(structured(x, y) for x, y in zip(a, b))
        return pairs / n
    if isinstance(a, bool) or isinstance(b, bool):
        # ``True == 1`` in Python; a boolean decision is not the number one.
        return 1.0 if isinstance(a, bool) and isinstance(b, bool) and a == b else 0.0
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return numeric(a, b)
    if isinstance(a, str) and isinstance(b, str):
        return 1.0 if a == b else jaccard(a, b)
    return exact(a, b)


_NAMED: dict[str, Comparator] = {
    "exact": exact,
    "jaccard": jaccard,
    "text": jaccard,
    "numeric": numeric,
    "structured": structured,
    "auto": structured,
}


def resolve_comparator(spec: str | Comparator | None) -> Comparator:
    """Accept a callable, a built-in name, or ``None`` for the default."""
    if spec is None:
        return structured
    if callable(spec):
        return spec
    try:
        return _NAMED[spec]
    except KeyError:
        raise ValueError(
            f"unknown comparator {spec!r}; expected one of {sorted(_NAMED)} or a callable"
        ) from None
