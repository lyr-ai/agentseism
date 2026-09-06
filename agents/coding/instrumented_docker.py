"""A Docker environment that records repository state after every action.

The point is to make the object of study observable without changing what is
studied. mini-swe-agent's trajectory records the command and its stdout, and
nothing about the repository: whether a command changed the working tree, which
files, and whether two runs that touched the same file produced the same
content. Reconstructing that from stdout is not possible -- `cat` reads and
writes depending only on a redirection, and the agent ran `git` once in 94
commands, for its own purposes.

So the state is probed here, in the environment, after each action:

    agent action  ->  DockerEnvironment.execute  ->  observation to the agent
                                    |
                                    +-> probe -> snapshot to a side file

The probe is a separate `docker exec`. Its output is never merged into the
returned observation, never appended to the message list, and never reaches the
model, so the agent's context is byte-identical to an uninstrumented run. This
is measurement, not intervention -- unlike changing a step budget or a prompt,
which would alter the agent being measured.

The snapshot is deliberately mechanical, so that "did the state change" is a
fact rather than a reading of intent::

    changed_files   sorted paths, tracked and untracked
    status          normalised `git status --porcelain`
    diff_hash       sha256 over status + `git diff HEAD` + untracked contents
    diff_bytes      size of that canonical form

`git diff HEAD` rather than `git diff`, so staged changes count. Untracked files
are hashed by content rather than staged with `git add -N`, which would mutate
the index the agent may later read.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from minisweagent.environments.docker import DockerEnvironment

PROBE = (
    "cd {repo} 2>/dev/null || exit 9; "
    "git diff --name-only HEAD; "
    "echo '<<<TRACKED_DIFF>>>'; "
    "git diff HEAD; "
    "echo '<<<UNTRACKED>>>'; "
    "git ls-files --others --exclude-standard -z "
    "| xargs -0 -r sha256sum 2>/dev/null"
)
"""Two levels of state, kept separate because they answer different questions.

`git diff HEAD` is the **source** state: what the repository would submit,
relative to the instance's base commit, staged changes included. Untracked files
are the rest of the **workspace**: scratch reproducers, debug scripts, and the
agent's own bookkeeping.

Both are recorded, because the boundary is not obvious in advance. In the
validation run the agent wrote `git diff -- ... > patch.txt`, which changed the
workspace and not one line of source. Deciding after the fact which files are
"real" would be picking the answer; recording both fingerprints leaves the
question open to whoever needs it later.
"""


def _changed_paths(name_only: str) -> list[str]:
    """Paths from `git diff --name-only`, one per line, no status prefix.

    An earlier version parsed `git status --porcelain` by slicing `line[3:]`,
    which assumes a two-character status and one space. That holds for ` M path`
    and `?? path` and not for renames (`R  old -> new`), and it silently ate the
    first character of every path: `astropy/...` was recorded as `stropy/...`.
    `--name-only` has no prefix to mis-slice.
    """
    return sorted(p.strip() for p in name_only.strip().splitlines() if p.strip())


def _untracked_paths(sha_lines: str) -> list[str]:
    """Paths from `sha256sum` output: `<64 hex>  <path>`."""
    out = []
    for line in sha_lines.strip().splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            out.append(parts[1].strip())
    return sorted(out)


class InstrumentedDockerEnvironment(DockerEnvironment):
    """`DockerEnvironment` plus a repository snapshot after each action.

    Extra config keys, both optional::

        probe_repo    path probed inside the container (default /testbed)
        probe_output  JSONL file the snapshots are written to
    """

    def __init__(self, *args, **kwargs):
        self._probe_repo = kwargs.pop("probe_repo", "/testbed")
        self._probe_output = kwargs.pop("probe_output", "") or os.getenv(
            "AGENTSEISM_PROBE_OUTPUT", ""
        )
        super().__init__(*args, **kwargs)
        self._step = 0
        self._previous: dict | None = None
        if self._probe_output:
            Path(self._probe_output).parent.mkdir(parents=True, exist_ok=True)

    def execute(self, action: dict, cwd: str = "", **kwargs) -> dict[str, Any]:
        output = super().execute(action, cwd, **kwargs)
        self._step += 1
        if self._probe_output:
            try:
                self._record(action, output)
            except Exception as exc:  # noqa: BLE001
                # A failed probe must never fail the run: the agent's execution
                # is the experiment, and the measurement is secondary to it.
                self._append({"step": self._step, "probe_error": repr(exc)})
        return output

    def _snapshot(self) -> dict[str, Any]:
        raw = subprocess.run(
            [
                self.config.executable, "exec", "-w", "/",
                self.container_id, *self.config.interpreter,
                PROBE.format(repo=self._probe_repo),
            ],
            text=True, capture_output=True, timeout=60,
        ).stdout
        names, _, rest = raw.partition("<<<TRACKED_DIFF>>>")
        diff, _, untracked = rest.partition("<<<UNTRACKED>>>")

        tracked = diff.strip()
        workspace = tracked + "\n<<<UNTRACKED>>>\n" + untracked.strip()
        return {
            "changed_files": _changed_paths(names),
            "untracked_files": _untracked_paths(untracked),
            "tracked_diff_hash": hashlib.sha256(tracked.encode()).hexdigest(),
            "workspace_diff_hash": hashlib.sha256(workspace.encode()).hexdigest(),
            "tracked_diff_bytes": len(tracked.encode()),
        }

    def _record(self, action: dict, output: dict) -> None:
        snap = self._snapshot()
        first = self._previous is None
        self._append({
            "step": self._step,
            "command": action.get("command", ""),
            "returncode": output.get("returncode"),
            "first_snapshot": first,
            # Two transitions, not one. `source_changed` is the repository the
            # instance would submit; `workspace_changed` also counts scratch
            # files and the agent's own bookkeeping.
            "source_changed": not first
            and snap["tracked_diff_hash"] != self._previous["tracked_diff_hash"],
            "workspace_changed": not first
            and snap["workspace_diff_hash"] != self._previous["workspace_diff_hash"],
            "timestamp": time.time(),
            **snap,
        })
        self._previous = snap

    def _append(self, row: dict) -> None:
        with open(self._probe_output, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
