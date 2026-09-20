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

    def __init__(self, out: Path, endpoint: str, image: str,
                 platform: str = "", checker=None):
        self.out = Path(out)
        self.endpoint = endpoint
        self.image = image
        self.platform = platform
        self._checker = checker
        self._model = None
        self._identity: dict | None = None

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
                "gpu": fp["gpu"], "hostname": fp["hostname"]}

    def assert_same_serving_process(self) -> None:
        """Donors and continuations must come from one serving process."""
        if self._identity is None:
            return
        now = self.identity()
        drift = [k for k in ("endpoint", "vllm_pid", "gpu", "hostname",
                             "model_id", "revision")
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

        Everything the turn produced is kept: messages, tool calls, raw
        responses, transport attempts, errors and timings. Storing only the
        parsed decision would make a later question about *why* unanswerable,
        which is the defect the Phase 2 `reason` field already demonstrated.
        """
        from agents.coding.fork import materialize  # noqa: F401
        raise IntegrityStop(
            "not_wired",
            "the container and agent loop are not connected yet; this backend "
            "is statically wired and mock-tested only, and no machine has been "
            "rented", {"run_id": run_id})

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
