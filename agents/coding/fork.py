"""Rebuild a recorded state, and resume an agent inside it.

The intervention in `paper/INTERVENTION_PREREG_H2.md` holds one thing fixed and
swaps another. What is held fixed is the tracked source state `S` at a point two
runs both passed through. What is swapped is the carried context: the message
log together with the untracked files that agent itself left in the workspace.

Those travel as one bundle and the reason is in the data. On
`pytest-dev__pytest-10051` the three runs reached the identical tracked state
`400ed404...` while holding three different scratch files -- `test_repro.py`,
`reproduce_issue.py`, `repro.py`. Attaching one run's transcript to another
run's workspace would put the agent in a context its own history contradicts: it
would read back a file it remembers writing and be told the file does not exist.
That is not a controlled contrast, it is an agent pushed off distribution.

So `materialize` restores source and workspace together, from one arm's archive,
and `forking` seeds the message log from the same arm.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from agents.coding.instrumented_docker import InstrumentedDockerEnvironment


class ForkMismatch(RuntimeError):
    """A rebuilt container does not carry the state it was rebuilt from.

    Raised rather than warned. A continuation from an unverified state measures
    something other than the experiment, and the pre-registration makes the
    reconstruction check a gate: a container that fails it is discarded and
    rebuilt, never used.
    """


def _copy_in(env: "InstrumentedDockerEnvironment", data: bytes, dest: str) -> None:
    subprocess.run(
        [env.config.executable, "cp", "-", f"{env.container_id}:{Path(dest).parent}"],
        input=_single_file_tar(Path(dest).name, data), check=True, capture_output=True,
    )


def _single_file_tar(name: str, data: bytes) -> bytes:
    import io
    import tarfile

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _run(env: "InstrumentedDockerEnvironment", script: str) -> tuple[int, str]:
    result = subprocess.run(
        [env.config.executable, "exec", "-w", "/", env.container_id,
         *env.config.interpreter, script],
        text=True, capture_output=True, timeout=300,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def load_step(step_dir: str | Path) -> dict[str, Any]:
    """Read one archived step: its diff bytes, its untracked tar, its messages."""
    directory = Path(step_dir)
    diff = directory / "tracked.diff"
    tar = directory / "untracked.tar"
    messages = directory / "messages.json"
    return {
        "dir": directory,
        "tracked_diff": diff.read_bytes() if diff.exists() else b"",
        "untracked_tar": tar.read_bytes() if tar.exists() else b"",
        "messages": json.loads(messages.read_text())["messages"] if messages.exists() else None,
    }


def materialize(
    step_dir: str | Path,
    image: str,
    expected: dict,
    *,
    repo: str = "/testbed",
    **env_kwargs,
) -> tuple["InstrumentedDockerEnvironment", dict]:
    """Start a container and put it into the archived state. Verify, or raise.

    `expected` is the probe row for that step, and the two fingerprints in it are
    the contract: `tracked_diff_hash` says the source came back, and
    `workspace_diff_hash` says the arm's own scratch files came back with it. A
    rebuild that reproduces the first and not the second is exactly the silent
    failure this experiment cannot afford, because it would leave the source
    controlled and the context only half-swapped.
    """
    # Imported here rather than at module scope: selecting a fork point and
    # seeding a forked agent are pure functions over recorded data, and they are
    # tested without Docker or an agent framework installed.
    from agents.coding.instrumented_docker import InstrumentedDockerEnvironment

    archived = load_step(step_dir)
    env = InstrumentedDockerEnvironment(image=image, probe_repo=repo, **env_kwargs)
    try:
        if archived["tracked_diff"]:
            _copy_in(env, archived["tracked_diff"], "/tmp/fork.diff")
            code, out = _run(env, f"cd {repo} && git apply --whitespace=nowarn /tmp/fork.diff && rm -f /tmp/fork.diff")
            if code != 0:
                raise ForkMismatch(f"git apply failed in {step_dir}: {out.strip()[:800]}")
        if archived["untracked_tar"]:
            _copy_in(env, archived["untracked_tar"], "/tmp/fork.tar")
            code, out = _run(env, f"cd {repo} && tar -xf /tmp/fork.tar && rm -f /tmp/fork.tar")
            if code != 0:
                raise ForkMismatch(f"untracked restore failed in {step_dir}: {out.strip()[:800]}")

        snapshot = env._snapshot()
        checks = {
            "tracked_diff_hash": (snapshot["tracked_diff_hash"], expected.get("tracked_diff_hash")),
            "workspace_diff_hash": (snapshot["workspace_diff_hash"], expected.get("workspace_diff_hash")),
        }
        bad = {k: v for k, v in checks.items() if v[1] and v[0] != v[1]}
        if bad:
            raise ForkMismatch(
                f"rebuilt state differs from {step_dir}: "
                + "; ".join(f"{k} got {g[:12]} want {w[:12]}" for k, (g, w) in bad.items())
            )
    except Exception:
        env.cleanup()
        raise
    return env, snapshot


def forking(base: type) -> type:
    """Wrap an agent class so `run()` starts from a donor's message log.

    `DefaultAgent.run` clears `self.messages` and seeds it with exactly two
    messages, system and instance, in a single `add_messages` call, then enters
    the loop. Replacing that one call is enough to change where the agent starts
    and leaves the loop itself untouched, which matters: a forked run has to be
    the same agent as an unforked one in every respect except its starting
    context, and a reimplemented loop would quietly stop being that.

    With `prefix_messages=None` the class behaves exactly like its base, which is
    what the fresh arm needs -- the same prompt, no narration of what was already
    done to the repository.
    """

    class _Forked(base):  # type: ignore[valid-type,misc]
        def __init__(self, *args, prefix_messages: list[dict] | None = None, **kwargs):
            self._prefix = list(prefix_messages) if prefix_messages else None
            self._seeded = False
            super().__init__(*args, **kwargs)

        def run(self, task: str = "", **kwargs) -> dict:
            self._seeded = False
            return super().run(task, **kwargs)

        def add_messages(self, *messages: dict) -> list[dict]:
            if not self._seeded:
                self._seeded = True
                if self._prefix is not None:
                    return super().add_messages(*self._prefix)
            return super().add_messages(*messages)

    _Forked.__name__ = f"Forked{base.__name__}"
    _Forked.__qualname__ = _Forked.__name__
    return _Forked
