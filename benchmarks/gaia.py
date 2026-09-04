"""GAIA task slices.

The slice is a *spec*, not a copy of the data: only task ids and the selection
rule are stored in this repository. GAIA is gated on Hugging Face, so anyone
reproducing an experiment loads the dataset themselves and gets the same tasks
from the same spec.

Selection rule for Week 1:

- validation split, Level 1 -- the level whose tasks are executable end to end
  without a long tool chain, so the first experiment measures agent variation
  rather than environment failure;
- no file attachment by default -- file extraction is its own source of
  variation and would confound the first measurement;
- sorted by ``task_id`` and truncated, so the slice is deterministic and does
  not depend on dataset row order.

Pilot first (10 tasks x 5 runs), then the full slice (50 x 10). The pilot exists
to find out whether the trace is stable and the outcome varies at all, before
paying for 500 executions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PILOT_SIZE = 10
WEEK1_SIZE = 50
SPEC_DIR = Path(__file__).resolve().parent


def load_gaia(level: str = "2023_level1", split: str = "validation") -> list[dict]:
    """Load GAIA rows via ``datasets``. Requires Hugging Face access to the gated repo."""
    try:
        from datasets import load_dataset
    except ImportError as err:  # pragma: no cover - environment dependent
        raise ImportError(
            "GAIA needs the 'datasets' package: pip install datasets. "
            "The dataset is gated; accept the terms at "
            "https://huggingface.co/datasets/gaia-benchmark/GAIA first."
        ) from err

    rows = load_dataset("gaia-benchmark/GAIA", level, split=split, trust_remote_code=True)
    return [dict(row) for row in rows]


def format_task(row: dict) -> dict:
    """One GAIA row as an AgentSeism case."""
    return {
        "id": row["task_id"],
        "input": {
            "task_id": row["task_id"],
            "question": row["Question"],
            "file_name": row.get("file_name") or "",
            "level": row.get("Level"),
        },
        "metadata": {"reference_answer": row.get("Final answer")},
    }


def select(
    rows: list[dict],
    size: int = PILOT_SIZE,
    *,
    require_no_file: bool = True,
) -> list[dict]:
    """Deterministically select ``size`` tasks, or fail loudly."""
    eligible = [r for r in rows if not (require_no_file and r.get("file_name"))]
    eligible.sort(key=lambda r: r["task_id"])
    if len(eligible) < size:
        raise ValueError(
            f"asked for {size} tasks but only {len(eligible)} match the selection rule "
            f"(level/split/require_no_file={require_no_file}); widen the rule explicitly "
            "rather than silently running a smaller slice"
        )
    return [format_task(r) for r in eligible[:size]]


def save_spec(tasks: list[dict], name: str) -> Path:
    """Record which tasks a run used -- ids only, no dataset content."""
    path = SPEC_DIR / f"gaia_{name}.json"
    path.write_text(
        json.dumps(
            {
                "dataset": "gaia-benchmark/GAIA",
                "config": "2023_level1",
                "split": "validation",
                "rule": "no file attachment, sorted by task_id, first N",
                "size": len(tasks),
                "task_ids": [t["id"] for t in tasks],
            },
            indent=2,
        )
    )
    return path


def load_spec(name: str) -> list[str]:
    """Task ids previously used, so a later run can reproduce the same slice."""
    path = SPEC_DIR / f"gaia_{name}.json"
    return json.loads(path.read_text())["task_ids"]


def tasks_from_spec(rows: list[dict], name: str) -> list[dict]:
    ids = set(load_spec(name))
    by_id = {r["task_id"]: r for r in rows}
    missing = ids - by_id.keys()
    if missing:
        raise ValueError(f"{len(missing)} task ids from spec '{name}' are not in the loaded rows")
    return [format_task(by_id[task_id]) for task_id in sorted(ids)]


def reference_answers(tasks: list[dict]) -> dict[str, Any]:
    return {t["id"]: t["metadata"].get("reference_answer") for t in tasks}
