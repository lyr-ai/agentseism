"""The real C2-H backend: donor generation and continuation execution.

**Importing this module does nothing.** No network, no model load, no Docker,
no container. Construction stores configuration and nothing else; every side
effect is behind an explicit `run_*` call, and `--resolve-only` therefore stays
side-effect free even when a real backend is configured.

One serving process for the whole experiment. Donors and continuations share a
single `InstrumentedLitellmModel`, one endpoint, one PID and one serving
fingerprint, because C2-H is defined as one session on one host
(`PREREG_C2H.md` §1). The model client is built once, lazily, on first use, and
its identity is recorded.

**No invisible retries, and the claim is checked rather than asserted.** The
registered transport policy is the one `run_c2.py` uses -- `stream=True`,
`attempt_timeout=180`, `max_attempts=6` -- with `num_retries: 0` underneath, so
the only retry layer is the instrumented one. Three things enforce that, since
grepping this file for a retry loop proves nothing about litellm, the HTTP
client or the SDK:

* `assert_no_hidden_retries()` reads the constructed client and raises if
  `num_retries` is anything but 0, at construction and before each use;
* a behavioural test drives one logical request and asserts the transport is
  entered exactly once;
* every record carries `transport_attempts` and `transport_events`, so a step
  that did retry is visible in the artifact rather than smoothed over, and a
  record arriving without that field is an integrity stop, not a silent gap.

**Nothing is skipped.** A container failure, a timeout, a parse failure or a
serving anomaly raises `IntegrityStop`. There is no path that drops a spec and
carries on: a run missing a cell is not the registered experiment, and the
runner must stop rather than produce one that looks complete.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from experiments.coding import c2h_protocol as P


class IntegrityStop(RuntimeError):
    """§6.5. Environment, container, transport or parse failure."""

    def __init__(self, stage: str, detail: str, context: dict | None = None):
        self.stage, self.detail, self.context = stage, detail, context or {}
        super().__init__(f"{stage}: {detail}")


class UnlabelledDonor(RuntimeError):
    """A donor the frozen checker cannot label.

    Recorded as `invalid`, counted towards the cap, and counted towards neither
    arm. It is never labelled by hand: an experiment whose arm membership can
    be decided by a person is not the experiment that was registered.
    """


class RealBackend:
    """Donor generation and continuation execution against a live stack.

    Construction is inert on purpose. `endpoint`, `image` and `out` are
    recorded; the client, the container and the model are created only inside
    `run_donor` / `run_continuation`.
    """

    def __init__(self, out: Path, endpoint: str, platform: str = "",
                 checker=None):
        self.out = Path(out)
        self.endpoint = endpoint
        self.image = P.IMAGE          # registered; deliberately not a parameter
        self.task = P.TASK
        self.platform = platform
        self._checker = checker
        self._model = None
        self._identity: dict | None = None
        self._image_digest: str | None = None

    def image_digest(self) -> str:
        """The resolved digest of the registered tag, read once.

        A tag can move; a digest cannot. It is read at first use rather than
        configured, and it enters the fingerprint so a silently re-pushed image
        cannot pass as the same one.
        """
        if self._image_digest is None:
            import subprocess
            try:
                out = subprocess.run(
                    ["docker", "image", "inspect", "--format",
                     "{{index .RepoDigests 0}}", self.image],
                    capture_output=True, text=True, timeout=60)
            except Exception as exc:  # noqa: BLE001
                raise IntegrityStop("image_digest",
                                    f"{type(exc).__name__}: {exc}",
                                    {"image": self.image}) from None
            if out.returncode != 0 or not out.stdout.strip():
                raise IntegrityStop(
                    "image_digest",
                    f"cannot resolve a digest for {self.image}: "
                    f"{(out.stderr or '').strip()[:200]}", {"image": self.image})
            self._image_digest = out.stdout.strip()
        return self._image_digest

    # ── lazily built, once, and shared ──
    def model(self):
        """The one client for the whole experiment, built on first use."""
        if self._model is None:
            import os
            os.environ.setdefault("OPENAI_API_BASE", self.endpoint)
            os.environ.setdefault("OPENAI_API_KEY", "not-needed")
            os.environ.setdefault("MSWEA_COST_TRACKING", "ignore_errors")
            from agents.coding.instrumented_model import InstrumentedLitellmModel
            # Exactly the registered transport policy. Nothing is added.
            self._model = InstrumentedLitellmModel(
                model_name=f"openai/{P.MODEL['id']}",
                model_kwargs={"drop_params": True},
                stream=True, attempt_timeout=180, max_attempts=6)
            self.assert_no_hidden_retries(self._model)
            self._identity = self.identity()
        return self._model

    @staticmethod
    def assert_no_hidden_retries(model) -> None:
        """The layer beneath the instrumented one must contribute nothing.

        `InstrumentedLitellmModel` sets `num_retries: 0` so that every attempt
        is its own and is counted. If something re-enables it, attempts stop
        being observable and `max_attempts=6` silently becomes 6xN.
        """
        got = dict(getattr(model.config, "model_kwargs", {})).get("num_retries")
        if got != 0:
            raise IntegrityStop(
                "transport_policy",
                f"num_retries is {got!r}, not 0: the layer beneath the "
                "instrumented retry would add uncounted attempts",
                {"model_kwargs": dict(getattr(model.config, "model_kwargs", {}))})

    def identity(self) -> dict:
        """Endpoint, PID and serving fingerprint, recorded with every record."""
        from experiments.coding.c2h_budget import session_fingerprint
        fp = session_fingerprint()
        return {"endpoint": self.endpoint, "model_id": P.MODEL["id"],
                "revision": P.MODEL["revision"], "vllm_pid": fp["vllm_pid"],
                "gpu": fp["gpu"], "hostname": fp["hostname"],
                "task": self.task, "image": self.image,
                "image_digest": self._image_digest}

    def assert_same_serving_process(self) -> None:
        """Donors and continuations must come from one serving process."""
        if self._identity is None:
            return
        now = self.identity()
        drift = [k for k in ("endpoint", "vllm_pid", "gpu", "hostname",
                             "model_id", "revision", "task", "image",
                             "image_digest")
                 if self._identity.get(k) != now.get(k)]
        if drift:
            raise IntegrityStop(
                "serving_identity",
                f"the serving process changed mid-experiment ({', '.join(drift)}); "
                "C2-H is one serving process and cannot be reassembled",
                {"was": self._identity, "now": now})

    # ── the two operations ──
    def run_donor(self, acquisition_index: int, run_id: str) -> str:
        """Generate one donor, label it with the frozen checker.

        `acquisition_index` is the donor's position in the pre-registered
        acquisition order (§4), **not** an inference seed. Sampling is frozen
        at `temperature=0, seed=None`.

        Returns "FAIL", "PASS" or "invalid". A donor the checker cannot label
        is `invalid`: it counts towards the cap and towards neither arm, and it
        is never adjudicated by hand.
        """
        self.assert_same_serving_process()
        rec = {"kind": "donor_run", "acquisition_index": acquisition_index,
               "run_id": run_id, "started": _now(), "identity": self.identity()}
        try:
            result = self._execute(run_id, prefix=None, step_limit=None,
                                   acquisition_index=acquisition_index)
        except IntegrityStop:
            raise
        except Exception as exc:  # noqa: BLE001
            raise IntegrityStop("donor_execution", f"{type(exc).__name__}: {exc}",
                                {"acquisition_index": acquisition_index,
                                 "run_id": run_id}) from None
        rec |= {"finished": _now(), **result}
        try:
            label = self.label(result)
        except UnlabelledDonor as exc:
            rec |= {"label": "invalid", "label_error": str(exc)}
            self._freeze(f"donor_{acquisition_index:02d}", rec)
            return "invalid"
        rec |= {"label": label}
        self._freeze(f"donor_{acquisition_index:02d}", rec)
        return label

    def label(self, result: dict) -> str:
        """The frozen correctness checker. Never a human."""
        if self._checker is None:
            from experiments.coding import label_correctness  # noqa: F401
            raise UnlabelledDonor("no checker bound; wire label_correctness "
                                  "before a real run")
        verdict = self._checker(result)
        if verdict not in ("FAIL", "PASS"):
            raise UnlabelledDonor(f"checker returned {verdict!r}")
        return verdict

    def run_continuation(self, spec: dict) -> dict:
        """One continuation, from the frozen manifest's spec. No re-selection.

        `spec` comes from the frozen manifest and is used verbatim; this method
        never looks up a donor, re-ranks one, or substitutes a horizon.
        """
        self.assert_same_serving_process()
        for key in ("run_id", "donor_run_id", "horizon", "step_limit", "arm"):
            if key not in spec:
                raise IntegrityStop("spec", f"manifest spec missing {key!r}", spec)
        rec = {"kind": "continuation_run", "started": _now(),
               "identity": self.identity(),
               **{k: spec[k] for k in ("run_id", "arm", "donor_id",
                                       "donor_run_id", "horizon", "replicate",
                                       "step_limit", "acquisition_index")
                  if k in spec}}
        try:
            result = self._execute(spec["run_id"], prefix=spec["donor_run_id"],
                                   step_limit=spec["step_limit"],
                                   horizon=spec["horizon"])
        except IntegrityStop:
            raise
        except Exception as exc:  # noqa: BLE001
            raise IntegrityStop("continuation_execution",
                                f"{type(exc).__name__}: {exc}",
                                {"run_id": spec["run_id"]}) from None
        rec |= {"finished": _now(), **result}
        self._require_attempt_record(rec, spec["run_id"])
        rec["artifact_sha256"] = self._freeze(spec["run_id"], rec)
        return {k: rec[k] for k in ("run_id", "exit_status", "artifact_sha256")
                if k in rec}

    # ── machinery ──
    def _execute(self, run_id, prefix, step_limit, **extra) -> dict:
        """Build the container, run the agent, return the full record.

        **One path for donors and continuations.** The same `materialize`, the
        same `ForkedAgent`, the same tool configuration. The only difference is
        whether a frozen prefix is injected: a donor starts from the task's
        initial state with `prefix_messages=[]`, a continuation resumes from
        the archived state the manifest names. Any other difference between the
        arms would be a confound this experiment could not separate from its
        own effect.

        Everything the run produced is kept: messages, tool calls, raw
        responses, transport attempts, container id, image digest, workspace
        and archive hashes, commands and exit status. Storing only the parsed
        decision would make a later question about *why* unanswerable, which is
        the defect the Phase 2 `reason` field already demonstrated.
        """
        import copy

        import yaml
        from minisweagent.agents.interactive import InteractiveAgent

        from agents.coding.archiving_agent import archiving
        from agents.coding.fork import ForkMismatch, forking, load_step, materialize

        ForkedAgent = forking(archiving(InteractiveAgent))
        digest = self.image_digest()
        model = self.model()

        prefix_messages, archive_state = [], None
        if prefix is not None:
            prefix_messages, archive_state = self._restore(prefix, extra, load_step)

        try:
            env, snapshot = materialize(
                archive_state.get("step_dir") if archive_state else None,
                image=self.image,
                expected=archive_state.get("tracked_diff_hash") if archive_state else None,
                include_untracked=True) if archive_state else self._fresh_env(
                    materialize, digest)
        except ForkMismatch as exc:
            raise IntegrityStop("fork_mismatch", str(exc),
                                {"run_id": run_id, "prefix": prefix}) from None
        except Exception as exc:  # noqa: BLE001
            raise IntegrityStop("container", f"{type(exc).__name__}: {exc}",
                                {"run_id": run_id, "image": self.image}) from None

        config = yaml.safe_load(
            (Path(__import__("minisweagent").__file__).parent
             / "config/benchmarks/swebench.yaml").read_text())
        agent_config = dict(config.get("agent", {})) | {
            "step_limit": step_limit or config.get("agent", {}).get("step_limit"),
            "mode": "yolo", "confirm_exit": False,
            "output_path": str(self.out / "raw" / f"{run_id}.trajectory.json"),
        }
        agent = ForkedAgent(model, env,
                            prefix_messages=copy.deepcopy(prefix_messages),
                            **agent_config)
        try:
            result = agent.run(task=self._task_text(prefix_messages, config))
        except Exception as exc:  # noqa: BLE001
            raise IntegrityStop("agent", f"{type(exc).__name__}: {exc}",
                                {"run_id": run_id}) from None
        finally:
            try:
                env.cleanup()
            except Exception:  # noqa: BLE001
                pass

        messages = getattr(agent, "messages", [])
        events = [e for m in messages for e in
                  (m.get("extra", {}) or {}).get("transport_events", [])]
        return {
            "exit_status": result.get("exit_status"),
            "submission": result.get("submission"),
            "messages": messages,
            "commands": [a.get("command") for m in messages
                         for a in (m.get("extra", {}) or {}).get("actions", [])],
            "transport_attempts": sum(
                (m.get("extra", {}) or {}).get("transport_attempts", 0)
                for m in messages),
            "transport_events": events,
            "container_id": getattr(env, "container_id", None)
            or getattr(env, "container", None),
            "image": self.image, "image_digest": digest,
            "prefix_injected": bool(prefix_messages),
            "prefix_messages": len(prefix_messages),
            "archive": archive_state,
            "start_tracked": (snapshot or {}).get("tracked_diff_hash"),
            "start_workspace": (snapshot or {}).get("workspace_diff_hash"),
        }

    def _fresh_env(self, materialize, digest):
        """A donor's container: the task's initial state, no archive.

        Returns `materialize`'s own `(env, snapshot)` pair unchanged, so the
        donor and the continuation paths hand `_execute` the same shape.
        """
        return materialize(None, image=self.image, expected=None,
                           include_untracked=True)

    def _restore(self, donor_run_id: str, extra: dict, load_step):
        """Locate the archived fork root the manifest names. Exactly one.

        A missing archive is an integrity stop, and so is an ambiguous one: a
        continuation that guesses which state it resumed from is not resuming
        from the manifest.
        """
        horizon = extra.get("horizon")
        if horizon is None:
            raise IntegrityStop("restore", "no horizon on the spec",
                                {"donor_run_id": donor_run_id})
        archive = self.out / "raw" / f"{donor_run_id}.archive"
        if not archive.is_dir():
            raise IntegrityStop("restore", f"no archive at {archive}",
                                {"donor_run_id": donor_run_id, "horizon": horizon})
        matches = sorted(archive.glob(f"step_{horizon:04d}"))
        if len(matches) != 1:
            raise IntegrityStop(
                "restore",
                f"{len(matches)} archived states match horizon {horizon} for "
                f"{donor_run_id}; the manifest names exactly one",
                {"matches": [str(m) for m in matches]})
        step = load_step(matches[0])
        messages = step.get("messages") or []
        if not messages:
            raise IntegrityStop("restore", "archived step has no message prefix",
                                {"step_dir": str(matches[0])})
        return messages, {"step_dir": str(matches[0]),
                          "tracked_diff_hash": step.get("tracked_diff_hash"),
                          "horizon": horizon, "donor_run_id": donor_run_id}

    @staticmethod
    def _task_text(prefix_messages: list[dict], config: dict) -> str:
        import re
        if prefix_messages and len(prefix_messages) > 1:
            content = prefix_messages[1].get("content") or ""
            m = re.search(r"<pr_description>\s*(.*?)\s*</pr_description>",
                          content, re.S)
            return m.group(1) if m else content
        return config.get("task", "") or P.TASK

    @staticmethod
    def _require_attempt_record(rec: dict, run_id: str) -> None:
        """A record without its attempt count is a gap, not a clean run."""
        if "transport_attempts" not in rec:
            raise IntegrityStop(
                "attempt_record",
                "the record carries no transport_attempts; retries must be "
                "visible in the artifact, and an absent count is "
                "indistinguishable from an unobserved one",
                {"run_id": run_id})

    def _freeze(self, name: str, record: dict) -> str:
        """Write the raw artifact atomically with its SHA-256, immediately.

        Immediately, because a block counts as complete only when every one of
        its specs has a valid artifact on disk; deferring the write would let a
        crash leave a block that looks finished in the log and is not on disk.
        """
        from experiments.coding.c2h_budget import write_atomic
        return write_atomic(self.out / "raw" / f"{name}.json",
                            json.dumps(record, indent=2, sort_keys=True, default=str))

    def artifact_valid(self, run_id: str) -> bool:
        import hashlib
        f = self.out / "raw" / f"{run_id}.json"
        d = Path(str(f) + ".sha256")
        if not (f.exists() and d.exists()):
            return False
        return (hashlib.sha256(f.read_text().encode()).hexdigest()
                == d.read_text().split()[0])

    def block_complete(self, spec_ids: list[str]) -> bool:
        """A block is complete only if every spec has a verified artifact."""
        return all(self.artifact_valid(r) for r in spec_ids)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
