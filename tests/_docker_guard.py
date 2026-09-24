"""Bound the Docker tests in time, and clean up what a wedge leaves behind.

A batch run sat for 49 minutes on `swebench.harness.run_evaluation` with the
process asleep at 0% CPU and an empty report directory, next to a container
idle for an hour. Nothing was failing and nothing was progressing.

The existing guards could not catch it. `subprocess.run(timeout=3600)` had not
fired yet, and SWE-bench's own `--timeout 1800` bounds a test inside a
container, not the harness waiting on the daemon.

Two decisions worth stating:

**A wedge fails; it does not skip.** Auto-skipping on timeout would hide a real
regression that happens to manifest as a hang, which is the same mistake as
treating a hang as a pass. The failure message names the condition instead, so
a wedge is never quietly folded into a verdict about the code.

**Cleanup runs either way.** Killing the process group leaves the containers it
started, and those are what the *next* run trips over.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess

import pytest

PROBE_TIMEOUT_SECONDS = 1500
"""Above a healthy run by a wide margin -- the F3 probe finishes in ~20 s and
the fullest module in under two minutes -- and far below the hour that a
wedge previously consumed."""

STRAY_NAME_FILTERS = ("minisweagent-", "sweb.eval")


def remove_stray_containers() -> list[str]:
    """Remove containers these tests start. Never touches anything else."""
    removed: list[str] = []
    for name in STRAY_NAME_FILTERS:
        ids = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"name={name}"],
            capture_output=True, text=True).stdout.split()
        for cid in ids:
            subprocess.run(["docker", "rm", "-f", cid],
                           capture_output=True, text=True)
            removed.append(f"{name}{cid}")
    return removed


def run_probe(argv: list[str], cwd, timeout: int = PROBE_TIMEOUT_SECONDS,
              env: dict | None = None) -> dict:
    """Run a probe under a wall clock, and leave nothing running behind it."""
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True,
                            start_new_session=True, env=env)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # The whole group: the probe's evaluator subprocess is what hangs, and
        # killing only the parent orphans it still holding the daemon.
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.communicate()
        stray = remove_stray_containers()
        pytest.fail(
            f"ENVIRONMENT WEDGE: no progress in {timeout}s. This is not a "
            f"verdict on the code -- the probe was killed and "
            f"{len(stray)} stray container(s) removed: {stray}. Re-run; if it "
            "wedges again, the hang is reproducible and worth locating.",
            pytrace=False)
    if proc.returncode != 0:
        remove_stray_containers()
        pytest.fail(f"probe exited {proc.returncode}\n{err[-3000:]}",
                    pytrace=False)
    remove_stray_containers()
    lines = out.strip().splitlines()
    assert lines, f"probe produced no output\n{err[-2000:]}"
    return json.loads(lines[-1])
