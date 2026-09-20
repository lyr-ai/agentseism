"""Running one task, and freezing what came out. No model, no container.

AgentSeism does not know how to run your agent. You tell it, with a shell
command or a Python callable, and it records what happened. That is the whole
adapter story in the first version: anything that takes a task and produces a
result already works.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunResult:
    task: str
    trial: int
    returncode: int
    seconds: float
    artifact_dir: str
    stdout: str = ""
    stderr: str = ""
    outcome: dict = field(default_factory=dict)
    invalid: bool = False
    invalid_reason: str = ""


class ShellRunner:
    """`command` with `{task_file}` and `{artifact_dir}` substituted."""

    def __init__(self, command: str, timeout: int = 3600):
        self.command, self.timeout = command, timeout

    def __call__(self, task_file: str, artifact_dir: str) -> dict:
        cmd = self.command.format(task_file=task_file, artifact_dir=artifact_dir)
        t0 = time.time()
        try:
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               timeout=self.timeout)
            return {"returncode": p.returncode, "stdout": p.stdout[-20000:],
                    "stderr": p.stderr[-20000:], "seconds": time.time() - t0}
        except subprocess.TimeoutExpired:
            # A timeout is not a failed task. It is a run we cannot score, and
            # the contract's invalid_policy decides what that means.
            return {"returncode": -1, "stdout": "", "stderr": "timeout",
                    "seconds": time.time() - t0, "invalid": True,
                    "invalid_reason": f"timeout after {self.timeout}s"}


class CallableRunner:
    """A Python function `(task_file, artifact_dir) -> dict`."""

    def __init__(self, fn):
        self.fn = fn

    def __call__(self, task_file: str, artifact_dir: str) -> dict:
        t0 = time.time()
        try:
            out = self.fn(task_file, artifact_dir) or {}
        except Exception as exc:  # noqa: BLE001
            return {"returncode": -1, "stderr": f"{type(exc).__name__}: {exc}",
                    "seconds": time.time() - t0, "invalid": True,
                    "invalid_reason": f"{type(exc).__name__}: {exc}"}
        return {"returncode": 0, "seconds": time.time() - t0, **out}


class ShellEvaluator:
    """Deterministic. Its stdout must be JSON; anything else is invalid.

    Not an LLM judge, and not parsed leniently: a scorer whose output can be
    interpreted two ways is a scorer that will eventually be interpreted the
    convenient way.
    """

    def __init__(self, command: str, timeout: int = 600):
        self.command, self.timeout = command, timeout

    def __call__(self, artifact_dir: str, run: dict) -> dict:
        cmd = self.command.format(artifact_dir=artifact_dir)
        try:
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return {"invalid": True, "invalid_reason": "evaluator timeout"}
        if p.returncode != 0:
            return {"invalid": True,
                    "invalid_reason": f"evaluator exit {p.returncode}: "
                                      f"{p.stderr.strip()[:200]}"}
        try:
            return json.loads(p.stdout)
        except json.JSONDecodeError:
            return {"invalid": True,
                    "invalid_reason": "evaluator stdout is not JSON"}


def run_trials(runner, evaluator, tasks: list[str], trials: int,
               out_dir: Path, arm: str, on_progress=None) -> list[RunResult]:
    """Every (task, trial). Results are written as they finish."""
    out_dir = Path(out_dir)
    results: list[RunResult] = []
    for task in tasks:
        for k in range(trials):
            art = out_dir / arm / Path(task).stem / f"trial_{k}"
            art.mkdir(parents=True, exist_ok=True)
            raw = runner(task, str(art))
            outcome = {} if raw.get("invalid") else evaluator(str(art), raw)
            invalid = bool(raw.get("invalid") or outcome.get("invalid"))
            r = RunResult(
                task=task, trial=k, returncode=raw.get("returncode", 0),
                seconds=round(raw.get("seconds", 0.0), 2), artifact_dir=str(art),
                stdout=raw.get("stdout", ""), stderr=raw.get("stderr", ""),
                outcome={} if invalid else outcome, invalid=invalid,
                invalid_reason=raw.get("invalid_reason")
                or outcome.get("invalid_reason", ""))
            results.append(r)
            (art / "run.json").write_text(json.dumps(r.__dict__, indent=2))
            if on_progress:
                on_progress(r)
    return results


def fingerprint(extra: dict | None = None) -> dict:
    """What must match for two arms to be comparable.

    Read from the environment rather than declared, because a value a user
    types is a value that can be wrong without anyone noticing.
    """
    def cmd(*a):
        try:
            return subprocess.run(a, capture_output=True, text=True,
                                  timeout=20).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""
    fp = {
        "model_revision": os.environ.get("AGENTSEISM_MODEL_REVISION", ""),
        "serving_runtime": os.environ.get("AGENTSEISM_SERVING_RUNTIME", ""),
        "dependency_lock": "",
        "prompt_version": os.environ.get("AGENTSEISM_PROMPT_VERSION", ""),
        "scaffold_version": os.environ.get("AGENTSEISM_SCAFFOLD_VERSION", ""),
        "gpu": cmd("nvidia-smi", "--query-gpu=name,driver_version",
                   "--format=csv,noheader"),
    }
    lock = Path("requirements.lock")
    for cand in (lock, Path("inference/requirements-vllm.lock.txt"),
                 Path("uv.lock"), Path("poetry.lock")):
        if cand.exists():
            fp["dependency_lock"] = hashlib.sha256(
                cand.read_bytes()).hexdigest()[:16]
            break
    return fp | (extra or {})
