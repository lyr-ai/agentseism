"""The registered infrastructure smoke test (amendment P.4).

One task, one arm, one run, to demonstrate that the dynamic chain is connected
— container, agent, challenge, evaluator, artifact. It is the **only** place
the chain may be shown to work, because constructibility can be checked
statically and a container that starts cannot.

What it is not: a measurement. It compares nothing, estimates nothing, and
**whether the task resolves is not a pass criterion**. A smoke test that
required success would be a difficulty filter wearing a plumbing test's name,
and `resolved: false` with the chain intact is a pass.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agentseism import pilot_protocol as P  # noqa: E402
from agentseism import real_backend as RB  # noqa: E402
from agentseism.budget import write_atomic  # noqa: E402

SMOKE_TASK = "pytest-dev__pytest-10051"
"""P.3 excludes it from the pilot, and that disqualification is what makes it
safe here: it cannot enter the draw, so using it cannot narrow or bias it."""

SMOKE_ARM = "baseline"
SMOKE_DIR = "data/runs/smoke"
ORDER_INDEX = -1
"""Outside the 18. A smoke run occupies no registered cell."""


class SmokeStop(RuntimeError):
    """The chain is not connected. Host 3 stops; no pilot run follows."""


def smoke_cell() -> dict:
    """The one registered smoke cell. Baseline arm, verbatim."""
    arm = P.ARMS[SMOKE_ARM]
    return {
        "order_index": ORDER_INDEX,
        "task": SMOKE_TASK,
        "arm": SMOKE_ARM,
        "replicate": 0,
        "step_limit": arm["step_limit"],
        "hint": arm["hint"],
        "challenge": arm["challenge"],
        "smoke": True,
        "pilot_evidence": False,
    }


# ── the six criteria: all about the chain, none about the outcome ──
def _image_started(r: dict) -> bool:
    return (r["infrastructure_status"] != RB.BACKEND_ERROR
            and int(r.get("n_calls", 0)) >= 1)


def _valid_tool_call(r: dict) -> bool:
    # The challenge fires on the first valid tool call, so FIRED is proof one
    # happened. NOT_ELIGIBLE is proof none did.
    return r["challenge_status"] == "FIRED"


def _challenge_injected_once(r: dict) -> bool:
    rec = r.get("challenge_record") or {}
    return (r.get("challenge_injections") == 1
            and r.get("suppressed_actions_executed") is False
            and "suppressed_actions" in rec
            and rec.get("injected_at_call") is not None)


def _termination_registered(r: dict) -> bool:
    # The codes must be distinguishable in the record, not merged: a run
    # stopped by its step budget and a run killed by the cost cap are
    # different facts.
    return (r["termination"] in P.TERMINATIONS
            and r["agent_termination_code"] in (
                P.COMPLETED, P.STEP_LIMIT_REACHED,
                P.FORMAT_ERROR_LIMIT_REACHED, P.NOT_ELIGIBLE)
            and P.STEP_LIMIT_REACHED != P.INFRA_TIMEOUT_1200S
            and r["infrastructure_status"] in (
                "OK", RB.INFRA_TIMEOUT_1200S, RB.BACKEND_ERROR))


def _evaluator_decided(r: dict) -> bool:
    # An explicit boolean. **Which** boolean is not consulted anywhere here.
    return isinstance(r.get("evaluator_resolved"), bool)


def _artifact_frozen(r: dict) -> bool:
    return bool(r.get("_artifact_verified"))


CRITERIA = (
    ("image_started", _image_started,
     "the task image ran and the agent executed inside it"),
    ("valid_tool_call", _valid_tool_call,
     "the agent produced at least one valid tool call"),
    ("challenge_injected_once", _challenge_injected_once,
     "the challenge fired exactly once and the original action was recorded, "
     "not executed"),
    ("termination_registered", _termination_registered,
     "the run ended with a registered code, with the step limit and the "
     "1200 s cap distinguishable"),
    ("evaluator_decided", _evaluator_decided,
     "the evaluator returned an explicit boolean resolved"),
    ("artifact_frozen", _artifact_frozen,
     "the artifact was written atomically and verifies against its digest"),
)

FORBIDDEN_IN_GATE = "evaluator_resolved is True"
"""A marker for the reverse test. No criterion may consult the *value* of the
verdict — only that it is a boolean. If task success is ever added to this
gate, `test_the_verdict_value_cannot_affect_the_gate` fails."""


def evaluate_chain(result: dict) -> dict:
    checks = {name: bool(fn(result)) for name, fn, _ in CRITERIA}
    return {
        "criteria": checks,
        "descriptions": {name: why for name, _, why in CRITERIA},
        "passed": all(checks.values()),
        "failed": sorted(k for k, v in checks.items() if not v),
    }


def run_smoke(config: RB.BackendConfig, out_dir: Path | str = SMOKE_DIR,
              backend=None, serving: dict | None = None, spec=None) -> dict:
    """Execute the one smoke cell, freeze it, and report on the chain.

    One execution. No retry, here or below: `run_cell` runs the agent once and
    the evaluator once, and a failure is reported rather than attempted again.

    `spec` is the registration the smoke is being run *for*. It defaults to
    the pilot, which is what every existing smoke artifact was written under,
    but it is not optional in effect: the artifact carries a `protocol_hash`
    and an `order_hash`, and stamping the pilot's onto an F3 host would put a
    closed experiment's identity into new evidence. The same defect as the
    preflight's plan and budget identities, in a third place.

    `serving` records the stack that answered it -- endpoint, model, revision,
    the vLLM pid, the dependency lock and the serving config. The pilot must
    run against the same values, and recording them here is what lets that be
    checked rather than assumed: a smoke test that proved a *different* stack
    works has proved nothing about the one that will serve the pilot.
    """
    out = Path(out_dir)
    if out.name != "smoke":
        raise SmokeStop(
            f"smoke output must go to a directory named 'smoke', not {out}. "
            "A smoke artifact in the pilot's tree would be indistinguishable "
            "from pilot evidence")
    out.mkdir(parents=True, exist_ok=True)

    cell = smoke_cell()
    result = (backend or RB.run_cell)(cell, config)
    RB.validate_result(result)

    sp = spec if spec is not None else P.SPEC
    payload = {
        "schema_version": P.SCHEMA_VERSION,
        "smoke": True,
        "pilot_evidence": False,
        "experiment": sp.name,
        "protocol_hash": sp.protocol_hash,
        "order_hash": sp.order_hash,
        "order_index": ORDER_INDEX,
        "task": cell["task"], "arm": cell["arm"],
        "step_limit": cell["step_limit"], "hint": cell["hint"],
        "timeout_seconds": config.timeout_seconds,
        "serving": dict(serving or {}),
        **result,
    }
    path = out / "smoke_run.json"
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    digest = write_atomic(path, body)
    verified = (hashlib.sha256(path.read_text().encode()).hexdigest() == digest
                and Path(str(path) + ".sha256").exists())

    chain = evaluate_chain({**result, "_artifact_verified": verified})
    report = {
        "smoke": True,
        "pilot_evidence": False,
        # The preflight embeds this report, and the CLI reads it from there.
        # It has to say which registration it proved a chain for.
        "experiment": sp.name,
        "protocol_hash": sp.protocol_hash,
        "order_hash": sp.order_hash,
        "task": SMOKE_TASK, "arm": SMOKE_ARM, "runs": 1,
        "artifact": str(path), "sha256": digest, "artifact_verified": verified,
        "evaluator_resolved": result["evaluator_resolved"],
        "outcome_state": result["outcome_state"],
        "serving": dict(serving or {}),
        "note": "resolved is reported, never gated on: whether the task was "
                "solved says nothing about whether the chain is connected",
        **chain,
    }
    write_atomic(out / "smoke_report.json",
                 json.dumps(report, indent=2, sort_keys=True, default=str))
    return report


def main(argv=None) -> int:
    """Run the registered smoke test on the instance, once."""
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--digests", required=True,
                    help="image_digests.tsv from the draw, plus the smoke task")
    ap.add_argument("--out", default=SMOKE_DIR)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--model-base-url", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--model-revision", required=True)
    # Recorded so the pilot's fingerprint can be checked against the stack the
    # smoke test actually exercised, rather than assumed to be the same one.
    ap.add_argument("--vllm-pid", default="")
    ap.add_argument("--dependency-lock-sha256", default="")
    ap.add_argument("--serving-config-sha256", default="")
    ap.add_argument("--experiment",
                    choices=("pilot", "f3", "engineering"), default="pilot",
                    help="the registration this smoke is run for; decides the "
                         "identity stamped on the artifact")
    args = ap.parse_args(argv)

    rows = [l.split("\t") for l in
            Path(args.digests).read_text().splitlines() if l.strip()]
    digests = {t: d for t, d in rows}
    if SMOKE_TASK not in digests:
        raise SystemExit(
            f"  the smoke task {SMOKE_TASK} has no frozen digest in "
            f"{args.digests}. Its image is pulled for the smoke test and "
            "frozen like any other; it is not fetched at run time")
    cfg = RB.BackendConfig(image_digests=digests, work_dir=Path(args.work_dir),
                           model_base_url=args.model_base_url,
                           model_name=args.model_name,
                           model_revision=args.model_revision)
    serving = {
        "model_base_url": args.model_base_url,
        "model_name": args.model_name,
        "model_revision": args.model_revision,
        "vllm_pid": args.vllm_pid,
        "dependency_lock_sha256": args.dependency_lock_sha256,
        "serving_config_sha256": args.serving_config_sha256,
    }
    from agentseism.pilot import SPECS
    rep = run_smoke(cfg, args.out, serving=serving,
                    spec=SPECS[args.experiment])
    for name, _, why in CRITERIA:
        mark = "ok  " if rep["criteria"][name] else "FAIL"
        print(f"  {name:<34} {mark}  {why}")
    print(f"  evaluator_resolved                 {rep['evaluator_resolved']!r} "
          "— reported, not gated on")
    if not rep["passed"]:
        raise SystemExit(f"  SMOKE FAILED: {', '.join(rep['failed'])}")
    print("  SMOKE PASS — the chain is connected; this is not pilot evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
