"""The real pilot backend: interface, result schema, and constructibility.

Host 2 reported `READY_FOR_MANUAL_PILOT_CONFIRMATION` with no runner in
existence, because preflight checked the environment and never checked that a
cell could execute. `build(dry_run=True)` is that missing check. It verifies
everything a cell needs *without running anything*: no container is created,
no image is pulled, no model request is sent, and the evaluator is inspected
but never invoked.

The result schema keeps three facts apart that a single `success` field would
merge:

    agent_termination_code   what the agent did          COMPLETED /
                             STEP_LIMIT_REACHED / NOT_ELIGIBLE
    infrastructure_status    whether the machinery held  OK /
                             INFRA_TIMEOUT_1200S / BACKEND_ERROR
    evaluator_resolved       the grader's verdict        True / False / None

Merging them is how a budget cap becomes a regression: a run killed at 1200 s
and a run that genuinely failed are the same number once both are `success: 0`.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agentseism import pilot_protocol as P  # noqa: E402

# ── outcome vocabulary ──
RESOLVED_TRUE = "RESOLVED_TRUE"
RESOLVED_FALSE = "RESOLVED_FALSE"
INFRA_TIMEOUT_1200S = P.INFRA_TIMEOUT_1200S
EVALUATOR_UNDECIDED = "EVALUATOR_UNDECIDED"
BACKEND_ERROR = "BACKEND_ERROR"

OUTCOME_STATES = (RESOLVED_TRUE, RESOLVED_FALSE, INFRA_TIMEOUT_1200S,
                  EVALUATOR_UNDECIDED, BACKEND_ERROR)

ENTERS_PILOT_OUTCOME = {
    RESOLVED_TRUE: True,
    RESOLVED_FALSE: True,
    INFRA_TIMEOUT_1200S: False,      # censored, never M1's effect
    EVALUATOR_UNDECIDED: False,      # integrity stop
    BACKEND_ERROR: False,            # integrity stop
}
"""Which terminal states may enter a pilot outcome.

`STEP_LIMIT_REACHED` is deliberately **not** an outcome state.

`STEP_LIMIT_REACHED` with `RESOLVED_TRUE` is legal and must stay legal: an
agent can make the fix on its last step and then exhaust its budget before
emitting a submission signal. A termination code may not overrule the grader. It is an
`agent_termination_code`, and it is scorable (`P.SCORABLE`): a step-limited run
is still graded, and its verdict is `RESOLVED_TRUE` or `RESOLVED_FALSE` like
any other. Making it a sixth mutually exclusive state would discard the
evaluator's verdict for exactly the runs M1 is about, which is the opposite of
letting it enter the outcome. The two axes are recorded separately so that
"reached the step limit" and "did not resolve" never collapse into one number.
"""


class BackendUnavailable(RuntimeError):
    """Constructibility failed. Preflight must not report READY."""


def outcome_state(infrastructure_status: str, evaluator_resolved) -> str:
    """Terminal state, by precedence: machinery, then grader."""
    if infrastructure_status == BACKEND_ERROR:
        return BACKEND_ERROR
    if infrastructure_status == INFRA_TIMEOUT_1200S:
        return INFRA_TIMEOUT_1200S
    if infrastructure_status != "OK":
        raise ValueError(f"unknown infrastructure_status {infrastructure_status!r}")
    if evaluator_resolved is None:
        return EVALUATOR_UNDECIDED
    if not isinstance(evaluator_resolved, bool):
        # A grader that answered something other than a boolean has not
        # decided, whatever it printed.
        return EVALUATOR_UNDECIDED
    return RESOLVED_TRUE if evaluator_resolved else RESOLVED_FALSE


def registered_termination(agent_termination_code: str,
                           infrastructure_status: str,
                           evaluator_resolved) -> str:
    """Map onto `P.TERMINATIONS`, which `run_pilot` validates against."""
    state = outcome_state(infrastructure_status, evaluator_resolved)
    if state == INFRA_TIMEOUT_1200S:
        return P.INFRA_TIMEOUT_1200S
    if state in (BACKEND_ERROR, EVALUATOR_UNDECIDED):
        return P.INVALID
    if agent_termination_code not in (P.COMPLETED, P.STEP_LIMIT_REACHED,
                                      P.FORMAT_ERROR_LIMIT_REACHED,
                                      P.NOT_ELIGIBLE):
        raise ValueError(f"unknown agent_termination_code "
                         f"{agent_termination_code!r}")
    return agent_termination_code


REQUIRED_RESULT_FIELDS = (
    "agent_termination_code", "infrastructure_status", "evaluator_resolved",
    "outcome_state", "enters_pilot_outcome", "termination",
    "challenge_status", "challenge_record", "recovered",
    "hint_sha256", "step_limit", "image_digest", "model_revision",
    "registered_model_id", "transport_model", "api_base",
    "transport_attempts", "evaluator_report_path", "n_calls",
    "elapsed_seconds",
)


def validate_result(r: dict) -> dict:
    """Refuse a result that has lost one of the three axes."""
    missing = [k for k in REQUIRED_RESULT_FIELDS if k not in r]
    if missing:
        raise ValueError(f"result is missing {missing}")
    if r["outcome_state"] not in OUTCOME_STATES:
        raise ValueError(f"unknown outcome_state {r['outcome_state']!r}")
    if r["outcome_state"] != outcome_state(r["infrastructure_status"],
                                           r["evaluator_resolved"]):
        raise ValueError("outcome_state does not follow from "
                         "infrastructure_status and evaluator_resolved")
    if r["enters_pilot_outcome"] is not ENTERS_PILOT_OUTCOME[r["outcome_state"]]:
        raise ValueError("enters_pilot_outcome contradicts the registered table")
    if r["termination"] not in P.TERMINATIONS:
        raise ValueError(f"unknown termination {r['termination']!r}")

    # ── four invariants: a termination code may never overrule a verdict,
    #    and a verdict may never be carried by a run whose machinery failed ──

    # 1. a RESOLVED_* state requires a real boolean from the grader
    if r["outcome_state"] in (RESOLVED_TRUE, RESOLVED_FALSE) \
            and not isinstance(r["evaluator_resolved"], bool):
        raise ValueError(f"{r['outcome_state']} requires evaluator_resolved to "
                         "be true or false, not "
                         f"{r['evaluator_resolved']!r}")

    # 2. a censored run carries no verdict and enters nothing
    if r["infrastructure_status"] == INFRA_TIMEOUT_1200S:
        if r["evaluator_resolved"] is not None:
            raise ValueError(
                "a run censored at the cap carries no verdict: it was stopped "
                "for cost, not graded, and a verdict attached to it would let "
                "the budget cap manufacture an outcome")
        if r["enters_pilot_outcome"]:
            raise ValueError("a censored run does not enter the pilot outcome")

    # 3. a step-limited run must actually have been graded
    if r["agent_termination_code"] in (P.STEP_LIMIT_REACHED,
                                       P.FORMAT_ERROR_LIMIT_REACHED) \
            and r["infrastructure_status"] == "OK" \
            and not r.get("evaluator_report_path"):
        raise ValueError(
            f"{r['agent_termination_code']} with healthy infrastructure must "
            "carry an evaluator report: the run ran out of a registered "
            "budget, which is M1's and M2's mechanism, and it is graded like "
            "any other. It may still be undecided -- it may not be ungraded")

    # 4. broken machinery never carries a verdict
    if r["infrastructure_status"] != "OK" and r["evaluator_resolved"] is not None:
        raise ValueError(
            f"infrastructure_status {r['infrastructure_status']} with "
            f"evaluator_resolved {r['evaluator_resolved']!r}: a run whose "
            "machinery failed has no verdict to report")
    if "success" in r:
        raise ValueError("a single `success` field merges the three axes; "
                         "record agent_termination_code, "
                         "infrastructure_status and evaluator_resolved")
    return r


@dataclasses.dataclass(frozen=True)
class BackendConfig:
    """Everything the backend needs, all of it frozen before run 0."""
    image_digests: dict           # task id -> repo digest, from the draw
    work_dir: Path
    model_base_url: str
    model_name: str
    model_revision: str
    timeout_seconds: int = P.RUN_TIMEOUT_SECONDS
    evaluator_dataset: str = "SWE-bench/SWE-bench_Verified"
    evaluator_split: str = "test"
    api_key: str = "not-needed"
    """A local vLLM needs no credential; LiteLLM needs the field present."""


# ── constructibility ──
def _check_hints() -> dict:
    try:
        P.verify_hints()
    except Exception as e:                                  # noqa: BLE001
        # verify_hints reads the installed package, so it fails for the same
        # reasons the backend does. Surface it as unconstructible rather than
        # as a bare traceback.
        raise BackendUnavailable(f"hints cannot be verified: {e}") from e
    for arm, spec in P.ARMS.items():
        if spec["hint"] not in P.HINTS:
            raise BackendUnavailable(f"arm {arm} names unfrozen hint "
                                     f"{spec['hint']!r}")
    return {"hints": sorted(P.HINTS), "sha256": dict(P.HINT_SHA256)}


def _check_agent() -> dict:
    try:
        from minisweagent.agents.default import AgentConfig, DefaultAgent
    except Exception as e:                                  # noqa: BLE001
        raise BackendUnavailable(f"mini-swe-agent is not importable: {e}") from e
    fields = set(getattr(AgentConfig, "model_fields", {}))
    for needed in ("step_limit", "wall_time_limit_seconds"):
        if needed not in fields:
            raise BackendUnavailable(
                f"AgentConfig has no {needed!r}; the registered mutation has "
                "no axis on this version")
    try:
        from experiments.coding.recovery_challenge import challenging
    except Exception as e:                                  # noqa: BLE001
        raise BackendUnavailable(f"challenge wrapper not importable: {e}") from e
    wrapped = challenging(DefaultAgent)
    if wrapped.step is DefaultAgent.step:
        raise BackendUnavailable("the challenge wrapper does not override step")
    if not isinstance(getattr(wrapped, "challenge_eligible", None), property):
        raise BackendUnavailable("the challenge wrapper exposes no "
                                 "challenge_eligible")
    return {"agent": DefaultAgent.__name__, "wrapped": wrapped.__name__,
            "agent_config_fields": sorted(fields)}


def _check_evaluator() -> dict:
    """Importable, signature-compatible, constructible. **Never invoked.**

    Calling it here would turn preflight into an unregistered execution, and
    the SWE-bench harness starts containers.
    """
    try:
        import swebench
        from swebench.harness import run_evaluation
    except Exception as e:                                  # noqa: BLE001
        raise BackendUnavailable(f"swebench is not importable: {e}") from e
    fn = getattr(run_evaluation, "main", None)
    if not callable(fn):
        raise BackendUnavailable("swebench.harness.run_evaluation has no main()")
    params = set(inspect.signature(fn).parameters)
    for needed in ("dataset_name", "split", "predictions_path", "run_id"):
        if needed not in params:
            raise BackendUnavailable(
                f"run_evaluation.main() has no {needed!r} parameter; the "
                "registered invocation does not fit this harness version")
    try:
        from experiments.coding.c2h_checker import label_from_report
    except Exception as e:                                  # noqa: BLE001
        raise BackendUnavailable(f"verdict reader not importable: {e}") from e
    if set(inspect.signature(label_from_report).parameters) < {"report"}:
        raise BackendUnavailable("label_from_report has no `report` parameter")
    return {"swebench": getattr(swebench, "__version__", "unknown"),
            "entry": "swebench.harness.run_evaluation:main",
            "invoked": False}


def _check_transport(cfg: BackendConfig) -> dict:
    """The address and the retry policy, verified **without sending anything**.

    Host 3 reached the container and failed on the first model call because
    the registered id went to LiteLLM bare. That was only reachable past a
    GPU and 31 GB of weights; it is checked here for free.
    """
    if not cfg.model_name:
        raise BackendUnavailable("no registered model id in the config")
    if "/" in cfg.model_name and cfg.model_name.split("/", 1)[0] in (
            "openai", "hosted_vllm", "huggingface", "azure"):
        raise BackendUnavailable(
            f"model_name {cfg.model_name!r} already carries a provider "
            "prefix. The registered id is the bare one; the prefix is added "
            "once, by transport_model()")
    try:
        addressed = P.transport_model(cfg.model_name)
    except ValueError as e:
        raise BackendUnavailable(str(e)) from e
    if not addressed.startswith(f"{P.LITELLM_PROVIDER}/"):
        raise BackendUnavailable(f"{addressed!r} carries no provider prefix")
    if not str(cfg.model_base_url).startswith("http"):
        raise BackendUnavailable(
            f"api_base {cfg.model_base_url!r} is not an endpoint")
    if not cfg.api_key:
        raise BackendUnavailable("LiteLLM needs an api_key field, even a dummy")

    try:
        import litellm
    except Exception as e:                                  # noqa: BLE001
        raise BackendUnavailable(f"litellm is not importable: {e}") from e
    sig = inspect.signature(litellm.completion)
    params = set(sig.parameters)
    # Any **kwargs accepts the knob, whatever it is named.
    takes_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD
                       for p in sig.parameters.values())
    for knob, value in P.RETRY_KNOBS.items():
        if value is None:
            continue
        if knob not in params and not takes_kwargs:
            raise BackendUnavailable(
                f"litellm.completion has no {knob!r}; the registered retry "
                "policy cannot be applied on this version")
        if value != 0:
            raise BackendUnavailable(
                f"retry knob {knob} is registered as {value}, not 0")

    # The layer that actually retried on host 3 is an environment variable,
    # not a config field. Setting one nothing reads looks identical to setting
    # one that works, so the installed source is checked.
    try:
        from minisweagent.models.utils import retry as _retry
        retry_src = inspect.getsource(_retry)
    except Exception as e:                                  # noqa: BLE001
        raise BackendUnavailable(
            f"cannot read the retry layer's source: {e}") from e
    assert_retry_env()          # in force in this process, not repaired here
    assert_cost_env()
    for var, value in P.RETRY_ENV.items():
        if var not in retry_src:
            raise BackendUnavailable(
                f"{var} is registered as the retry control but the installed "
                "retry layer does not read it; the policy would be set and "
                "have no effect")
        if int(value) != 1:
            raise BackendUnavailable(
                f"{var} is registered as {value!r}, not '1'")
    return {"registered_model_id": cfg.model_name,
            "transport_model": addressed,
            "api_base": cfg.model_base_url,
            "attempts": P.TRANSPORT_ATTEMPTS,
            "retry_knobs": {k: v for k, v in P.RETRY_KNOBS.items()},
            "retry_env": dict(P.RETRY_ENV),
            "retry_env_in_process": {k: __import__("os").environ.get(k)
                                     for k in P.RETRY_ENV},
            "cost_tracking": P.COST_TRACKING,
            "cost_env_in_process": {k: __import__("os").environ.get(k)
                                    for k in P.COST_ENV},
            "requests_sent": 0}


def _check_images(cfg: BackendConfig) -> dict:
    """Confirm each frozen digest against **local** image metadata.

    `docker image inspect` reads what is already on the host. A missing image
    is a failure, never a pull: fetching one here would make preflight change
    the thing it is checking, and a digest that arrives during preflight was
    not the digest that was frozen.
    """
    if not shutil.which("docker"):
        raise BackendUnavailable("docker is not on PATH")
    if not cfg.image_digests:
        raise BackendUnavailable("no frozen image digests were supplied")
    seen = {}
    for task, frozen in sorted(cfg.image_digests.items()):
        r = subprocess.run(
            ["docker", "image", "inspect", frozen.split("@")[0],
             "--format", "{{json .RepoDigests}}"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise BackendUnavailable(
                f"{task}: image {frozen.split('@')[0]} is not present on this "
                "host. Preflight does not pull: a digest that arrives now was "
                "not the digest that was frozen")
        local = json.loads(r.stdout or "[]")
        if frozen not in local:
            raise BackendUnavailable(
                f"{task}: local digests {local} do not include the frozen "
                f"{frozen}")
        seen[task] = frozen
    return {"images": seen, "pulled": False}


def _check_execution_path() -> dict:
    """The check host 2 did not have: is there a runner at all?"""
    fn = globals().get("run_cell")
    if fn is None:
        raise BackendUnavailable(
            "real_backend.run_cell is not implemented. This is the condition "
            "that let host 2 report READY with no runner: the environment was "
            "verified and the execution path was not")
    if getattr(fn, "placeholder", False):
        raise BackendUnavailable("real_backend.run_cell is a placeholder")
    params = list(inspect.signature(fn).parameters)
    if params[:2] != ["cell", "config"]:
        raise BackendUnavailable(
            f"run_cell{tuple(params)} does not take (cell, config)")
    return {"run_cell": "present"}


def build(config: BackendConfig | None = None, *, dry_run: bool = False):
    """Construct the backend, or verify that it could be constructed.

    `dry_run=True` performs every check and returns a report. It creates no
    container, pulls no image, sends no model request and does not invoke the
    evaluator.
    """
    report = {
        "hints": _check_hints(),
        "agent": _check_agent(),
        "evaluator": _check_evaluator(),
        "execution_path": _check_execution_path(),
        "containers_created": 0,
        "images_pulled": 0,
        "model_requests": 0,
        "evaluator_invocations": 0,
    }
    if config is not None:
        report["transport"] = _check_transport(config)
        report["images"] = _check_images(config)
    if dry_run:
        report["dry_run"] = True
        return report
    if config is None:
        raise BackendUnavailable("a BackendConfig is required to build a runner")
    return lambda cell: validate_result(run_cell(cell, config))  # noqa: F821


# ════════════════════════════════════════════════════════════════════════
# the execution path
# ════════════════════════════════════════════════════════════════════════
class CellError(RuntimeError):
    """A protocol violation in the cell itself. Not an outcome: a stop."""


def _swebench_base() -> dict:
    """The upstream benchmark config the pilot builds on, read once."""
    import os

    import minisweagent
    import yaml
    path = os.path.join(os.path.dirname(minisweagent.__file__),
                        "config/benchmarks/swebench.yaml")
    return yaml.safe_load(open(path))


def _resolve_hint(cell: dict) -> tuple[str, str]:
    """Exact index into the frozen table. No fallback, no transformation."""
    key = cell["hint"]
    if key not in P.HINTS:
        raise CellError(
            f"cell names hint {key!r}, which is not in the frozen HINTS "
            f"{sorted(P.HINTS)}. The pilot does not invent a template")
    return P.HINTS[key], P.HINT_SHA256[key]


def _resolve_image(cell: dict, config: BackendConfig) -> str:
    """A digest, never a tag. `:latest` moves; `@sha256:` does not."""
    task = cell["task"]
    if task not in config.image_digests:
        raise CellError(f"no frozen image digest for task {task!r}")
    ref = config.image_digests[task]
    if "@sha256:" not in ref:
        raise CellError(
            f"image reference {ref!r} for {task} is not digest-pinned; a tag "
            "can move between the draw and the run")
    return ref


def _problem_statement(task: str, config: BackendConfig) -> str:
    from datasets import load_dataset
    ds = load_dataset(config.evaluator_dataset, split=config.evaluator_split)
    rows = [r for r in ds if r["instance_id"] == task]
    if len(rows) != 1:
        raise CellError(f"{len(rows)} rows for {task!r} in "
                        f"{config.evaluator_dataset}")
    return rows[0]["problem_statement"]


def _recovered(messages: list[dict], injected_at_call: int) -> bool:
    """Did a valid tool call follow the injected error?

    Read from the transcript rather than inferred from the exit status: an
    agent can recover and still run out of steps later, and those are
    different facts.
    """
    seen = 0
    for m in messages:
        extra = m.get("extra") or {}
        if extra.get("actions"):
            seen += 1
            if seen > injected_at_call:
                return True
    return False


def model_config(config: BackendConfig, hint: str) -> dict:
    """The model section the pilot serves with. Separated so the transport
    probe can exercise the real thing rather than a copy of it."""
    base = _swebench_base()
    model_cfg = dict(base["model"])
    model_cfg["format_error_template"] = hint          # the M2 axis, exactly
    # The registered id is what the server serves; the prefix is how the
    # client addresses it. Host 3 reached the container and then failed on
    # `LLM Provider NOT provided` because the bare id went to LiteLLM.
    model_cfg["model_name"] = P.transport_model(config.model_name)
    # LiteLLM prices a response *after* generating it, and a locally served
    # model has no price entry -- so the answer is discarded by accounting the
    # pilot does not need. Spend is read from the billing page, never from a
    # price table. Set on the config because the environment variable behind
    # this field is read at import time.
    model_cfg["cost_tracking"] = P.COST_TRACKING
    model_cfg["model_kwargs"] = {
        **model_cfg.get("model_kwargs", {}),
        "api_base": config.model_base_url,
        "api_key": config.api_key,
        # One logical request, one transport attempt (P.8). A knob left at its
        # default is a policy nobody registered.
        **{k: v for k, v in P.RETRY_KNOBS.items() if v is not None},
    }
    return model_cfg


def assert_cost_env() -> dict:
    """Verify the cost-tracking environment. **Never set it.**

    The config field is the mechanism that holds; this checks that the
    environment agrees, so the two cannot drift apart silently.
    """
    import os
    for k, want in P.COST_ENV.items():
        got = os.environ.get(k)
        if got != want:
            raise BackendUnavailable(
                f"{k} is {got!r}, registered as {want!r}. It is read at "
                "import time, so it must be exported before Python starts; "
                "the backend verifies it and does not repair it")
    return dict(P.COST_ENV)


def assert_retry_env() -> dict:
    """Verify the retry variable. **Never set it.**

    `minisweagent`'s query loop is tenacity with `stop_after_attempt` read from
    the environment, defaulting to ten -- the nine retries host 3 logged, which
    no LiteLLM knob touches.

    Measured on 2.4.6, the value is read inside `retry()` on every call, so
    setting it after import does take effect. The backend still refuses to set
    it, for two reasons. A process that repairs its own transport policy cannot
    report whether the policy was in force when it started, and the guarantee
    would silently depend on an implementation detail that a later version is
    free to change to import-time evaluation. It is exported by the shell
    before any Python starts, and checked here.
    """
    import os
    for k, want in P.RETRY_ENV.items():
        got = os.environ.get(k)
        if got != want:
            raise BackendUnavailable(
                f"{k} is {got!r}, registered as {want!r}. It must be exported "
                "before Python starts -- the backend verifies it and does not "
                "repair it, so that the artifact records the policy that was "
                "actually in force")
    return dict(P.RETRY_ENV)


def _agent_result(cell: dict, config: BackendConfig, hint: str, image: str):
    """One agent execution. No retry: a cell is one run."""
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments import get_environment
    from minisweagent.models import get_model

    from experiments.coding.recovery_challenge import challenging

    assert_retry_env()
    assert_cost_env()
    base = _swebench_base()
    model_cfg = model_config(config, hint)
    env_cfg = dict(base["environment"])
    env_cfg["image"] = image                           # digest-pinned
    agent_cfg = dict(base["agent"])
    agent_cfg["step_limit"] = cell["step_limit"]       # the M1 axis
    agent_cfg["cost_limit"] = P.COST_LIMIT_DISABLED    # makes LimitsExceeded
    agent_cfg["wall_time_limit_seconds"] = config.timeout_seconds

    model = get_model(model_cfg["model_name"], config=model_cfg)
    env = get_environment(env_cfg, default_type="docker")
    agent = challenging(DefaultAgent)(model, env, **agent_cfg)
    info = agent.run(task=_problem_statement(cell["task"], config))
    return agent, info


def _map_exit(agent, info: dict, cell: dict) -> str:
    """Registered mapping, with the one assertion P.6 requires."""
    status = str(info.get("exit_status") or "")
    if status not in P.EXIT_STATUS_MAP:
        raise CellError(f"unmapped agent exit status {status!r}; "
                        f"{sorted(P.EXIT_STATUS_MAP)} are registered")
    code = P.EXIT_STATUS_MAP[status]
    if code == P.STEP_LIMIT_REACHED:
        # LimitsExceeded serves both limits and names neither. The cost branch
        # is unreachable (cost_limit 0), so this must be the step limit -- and
        # if the counter disagrees it is a misclassification, not a step limit.
        if int(getattr(agent, "n_calls", 0)) < int(cell["step_limit"]):
            raise CellError(
                f"LimitsExceeded at n_calls={getattr(agent, 'n_calls', None)} "
                f"below step_limit={cell['step_limit']}: the exception did not "
                "come from the step limit and the mapping does not hold")
    return code


def _evaluate(cell: dict, submission: str, config: BackendConfig) -> tuple:
    """One evaluator execution against this cell's own patch.

    Returns `(resolved, report_path)`. `resolved` is `True`/`False` only when
    the report says so in a boolean; anything else is `None`, which becomes
    EVALUATOR_UNDECIDED rather than a failure.
    """
    run_id = (f"pilot_{cell['order_index']:02d}_{cell['task']}_"
              f"{cell['arm']}_r{cell['replicate']}")
    work = Path(config.work_dir) / "eval"
    work.mkdir(parents=True, exist_ok=True)
    pred = work / f"{run_id}.jsonl"
    pred.write_text(json.dumps({
        "instance_id": cell["task"],
        "model_name_or_path": run_id,
        "model_patch": submission or "",
    }) + "\n")
    reports = work / "reports"
    reports.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "swebench.harness.run_evaluation",
         "--dataset_name", config.evaluator_dataset,
         "--split", config.evaluator_split,
         "--predictions_path", str(pred), "--run_id", run_id,
         "--max_workers", "1", "--timeout", "1800",
         "--report_dir", str(reports)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3600)
    path = _instance_report(run_id, cell["task"])
    if path is None:
        return None, ""
    return _verdict(json.loads(path.read_text()), cell["task"]), str(path)


def _instance_report(run_id: str, task: str) -> Path | None:
    """The harness's **per-instance** report, which is the authoritative one.

    The run-level summary it also writes has no per-instance `resolved` field
    and can disagree: a real run graded this task `resolved: False` with 15
    PASS_TO_PASS successes while the summary filed it under
    `ambiguous_failure_ids / no_tests_collected`. A mocked evaluator hid both
    facts.
    """
    for root in (Path("logs/run_evaluation") / run_id,
                 Path("logs/run_evaluation")):
        if not root.exists():
            continue
        hits = sorted(root.rglob(f"{task}/report.json"))
        if hits:
            return hits[-1]
    return None


def _verdict(report: dict, task: str):
    """True, False, or None -- via the checker this project already had.

    `c2h_checker.label_from_report` was written for the donor batch and
    verified 20/20 offline. The pilot reimplemented it, badly, against the
    wrong file. Reusing it is the point: an infra failure, a missing patch, a
    patch that did not apply and an absent `resolved` are each **undecided**,
    never False.
    """
    try:
        from experiments.coding.c2h_checker import (UnlabelledDonor,
                                                    label_from_report)
    except Exception:                                       # noqa: BLE001
        return None
    try:
        return label_from_report(report, task) == "PASS"
    except UnlabelledDonor:
        return None


def run_cell(cell: dict, config: BackendConfig) -> dict:
    """Execute one registered cell: agent once, evaluator once.

    No retry at any level. Infrastructure trouble -- a container that will not
    start, a transcript that will not parse, an evaluator that crashes --
    becomes BACKEND_ERROR with no verdict. It never becomes RESOLVED_FALSE,
    because a broken machine and a failed fix are different facts and merging
    them lets the machine's health move the result.
    """
    import time
    t0 = time.time()
    hint, hint_sha = _resolve_hint(cell)
    image = _resolve_image(cell, config)

    agent = None
    try:
        agent, info = _agent_result(cell, config, hint, image)
        code = _map_exit(agent, info, cell)
        submission = info.get("submission") or ""
    except CellError:
        raise
    except Exception as e:                                   # noqa: BLE001
        return _error_result(cell, hint_sha, image, config, t0,
                             f"{type(e).__name__}: {e}", agent)

    fired = bool(getattr(agent, "challenge_fired", False))
    record = getattr(agent, "challenge_record", None)
    if not fired:
        # No first valid tool call, so nothing was injected. Out of M2's
        # recovery denominator, and never a recovery failure.
        code = P.NOT_ELIGIBLE
    elif not record or "suppressed_actions" not in record:
        return _error_result(cell, hint_sha, image, config, t0,
                             "the challenge fired but left no record",
                             agent)

    if code == P.INFRA_TIMEOUT_1200S:
        # Censored for cost. Not graded, and carrying no verdict.
        return _result(cell, hint_sha, image, config, t0, agent,
                       agent_termination_code=P.COMPLETED,
                       infrastructure_status=INFRA_TIMEOUT_1200S,
                       evaluator_resolved=None, report_path="",
                       fired=fired, record=record)

    try:
        resolved, report_path = _evaluate(cell, submission, config)
    except Exception as e:                                   # noqa: BLE001
        return _error_result(cell, hint_sha, image, config, t0,
                             f"evaluator: {type(e).__name__}: {e}", agent)

    return _result(cell, hint_sha, image, config, t0, agent,
                   agent_termination_code=code,
                   infrastructure_status="OK",
                   evaluator_resolved=resolved, report_path=report_path,
                   fired=fired, record=record)


def _result(cell, hint_sha, image, config, t0, agent, *,
            agent_termination_code, infrastructure_status, evaluator_resolved,
            report_path, fired, record) -> dict:
    import time
    injected = (record or {}).get("injected_at_call")
    messages = list(getattr(agent, "messages", []) or [])
    r = {
        "agent_termination_code": agent_termination_code,
        "infrastructure_status": infrastructure_status,
        "evaluator_resolved": evaluator_resolved,
        "challenge_status": "FIRED" if fired else P.NOT_ELIGIBLE,
        "challenge_record": record,
        "challenge_injections": 1 if fired else 0,
        "suppressed_actions_executed": False,
        "recovered": (_recovered(messages, injected)
                      if fired and injected is not None else None),
        "hint_sha256": hint_sha,
        "step_limit": cell["step_limit"],
        "image_digest": image,
        # Three separate fields so the registered id is never confused with
        # how it was addressed.
        "registered_model_id": config.model_name,
        "transport_model": P.transport_model(config.model_name),
        "api_base": config.model_base_url,
        "transport_attempts": P.TRANSPORT_ATTEMPTS,
        "cost_tracking": P.COST_TRACKING,
        "model_revision": config.model_revision,
        "evaluator_report_path": report_path,
        "n_calls": int(getattr(agent, "n_calls", 0)),
        "elapsed_seconds": round(time.time() - t0, 2),
        "cost": float(getattr(agent, "cost", 0.0)),
        "messages": messages,
    }
    r["outcome_state"] = outcome_state(infrastructure_status, evaluator_resolved)
    r["enters_pilot_outcome"] = ENTERS_PILOT_OUTCOME[r["outcome_state"]]
    r["termination"] = registered_termination(
        agent_termination_code, infrastructure_status, evaluator_resolved)
    return validate_result(r)


def _error_result(cell, hint_sha, image, config, t0, detail, agent) -> dict:
    import time
    return validate_result({
        "agent_termination_code": P.COMPLETED,
        "infrastructure_status": BACKEND_ERROR,
        "evaluator_resolved": None,
        "outcome_state": BACKEND_ERROR,
        "enters_pilot_outcome": False,
        "termination": P.INVALID,
        "challenge_status": P.NOT_ELIGIBLE,
        "challenge_record": getattr(agent, "challenge_record", None),
        "challenge_injections": int(bool(getattr(agent, "challenge_fired", False))),
        "suppressed_actions_executed": False,
        "recovered": None,
        "hint_sha256": hint_sha,
        "step_limit": cell["step_limit"],
        "image_digest": image,
        "registered_model_id": config.model_name,
        "transport_model": P.transport_model(config.model_name)
                           if config.model_name else "",
        "api_base": config.model_base_url,
        "transport_attempts": P.TRANSPORT_ATTEMPTS,
        "model_revision": config.model_revision,
        "evaluator_report_path": "",
        "n_calls": int(getattr(agent, "n_calls", 0)),
        "elapsed_seconds": round(time.time() - t0, 2),
        "backend_error": detail,
        "messages": list(getattr(agent, "messages", []) or []),
    })
