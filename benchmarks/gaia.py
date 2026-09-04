"""GAIA task slices.

The slice is a *spec*, not a copy of the data: only task ids and the selection
rule are stored in this repository. GAIA is gated on Hugging Face, so anyone
reproducing an experiment loads the dataset themselves and gets the same tasks
from the same spec.

Selection rule for Week 1:

- validation split, Level 1 (53 tasks) -- the level whose tasks are executable
  end to end without a long tool chain, so the first experiment measures agent
  variation rather than environment failure;
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

REPO_ID = "gaia-benchmark/GAIA"
METADATA = "2023/{split}/metadata.level{level}.parquet"
"""Current layout of the GAIA repo: parquet metadata per split and level. The
older loading-script API (``load_dataset(..., "2023_level1", trust_remote_code=True)``)
does not match what the repo ships today."""

PILOT_SIZE = 10
WEEK1_SIZE = 50
SPEC_DIR = Path(__file__).resolve().parent


def check_access() -> tuple[bool, str]:
    """Preflight: is this machine authorized to read GAIA?

    Two failures look alike from a distance and are fixed differently:
    being logged out, and being logged in but not on the authorized list.
    Gated access needs the conditions accepted on the dataset page; a
    ``huggingface-cli login`` alone is not enough.
    """
    try:
        from huggingface_hub import HfApi, whoami
    except ImportError:  # pragma: no cover - environment dependent
        return False, "huggingface_hub is not installed: pip install huggingface_hub pandas pyarrow"

    try:
        user = whoami()["name"]
    except Exception:
        return False, "not logged in: run `huggingface-cli login`"

    try:
        HfApi().hf_hub_download(
            repo_id=REPO_ID,
            filename=METADATA.format(split="validation", level=1),
            repo_type="dataset",
        )
    except Exception as err:
        if "gated" in str(err).lower() or "restricted" in str(err).lower():
            return False, (
                f"logged in as {user}, but not authorized for {REPO_ID}. "
                f"Accept the conditions at https://huggingface.co/datasets/{REPO_ID} "
                "while signed in as that user; logging in is a separate step from "
                "being granted access."
            )
        return False, f"{type(err).__name__}: {err}"
    return True, f"authorized as {user}"


def load_gaia(level: int = 1, split: str = "validation") -> list[dict]:
    """Load GAIA metadata rows straight from the repo's parquet files."""
    try:
        from huggingface_hub import hf_hub_download
        import pandas as pd
    except ImportError as err:  # pragma: no cover - environment dependent
        raise ImportError(
            "GAIA needs huggingface_hub and pandas: pip install huggingface_hub pandas pyarrow"
        ) from err

    ok, message = check_access()
    if not ok:
        raise PermissionError(message)

    path = hf_hub_download(
        repo_id=REPO_ID,
        filename=METADATA.format(split=split, level=level),
        repo_type="dataset",
    )
    return pd.read_parquet(path).to_dict("records")


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


def main() -> None:
    """Preflight and slice selection: `python benchmarks/gaia.py`."""
    ok, message = check_access()
    print(("OK   " if ok else "FAIL ") + message)
    if not ok:
        raise SystemExit(1)

    rows = load_gaia()
    with_files = sum(1 for r in rows if r.get("file_name"))
    print(f"level 1 validation: {len(rows)} tasks, {with_files} with attachments")

    tasks = select(rows, PILOT_SIZE)
    path = save_spec(tasks, "pilot")
    print(f"pilot slice: {len(tasks)} tasks -> {path}")
    for task in tasks:
        print(f"  {task['id']}  {task['input']['question'][:70]}")


if __name__ == "__main__":
    main()
