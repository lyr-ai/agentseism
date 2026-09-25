"""Run the coding agent on one SWE-bench instance, in AgentSeism's runner shape.

    swebench_runner.py --task <task.json> --out <artifact_dir>

AgentSeism's runner contract is `--task {task_file} --out {artifact_dir}` and
nothing else; this is the whole adapter. It deliberately keeps SWE-bench
knowledge on this side of the boundary: AgentSeism core learns nothing about
instances, images or patches, and this script learns nothing about verdicts,
thresholds or comparability.

The agent configuration is read from `agent_config.json` beside this file,
because the thing under test is a *repository change*. A pull request that cuts
`step_limit` is what CI compares; a flag passed by the harness would not be.

Writes into the artifact directory:

    patch.diff      the agent's submission, empty if it produced none
    agent_run.json  instance, exit status, step limit, model, timings

Not `run.json`: AgentSeism writes its own `RunResult` under that name into the
same directory after the evaluator returns, so a runner that used it would have
its metadata silently overwritten.

Prompts are mini-swe-agent's registered SWE-bench templates; only `step_limit`
and the model are taken from `agent_config.json`.

It scores nothing. Whether the patch is correct is the evaluator's question,
answered separately and deterministically.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "agent_config.json"
REGISTRY = "docker.io/swebench/sweb.eval.x86_64"


def image_for(instance_id: str) -> str:
    """The official SWE-bench image name, built the way the rest of the
    repository builds it: `__` becomes `_1776_`, once, lowercased."""
    return f"{REGISTRY}.{instance_id.replace('__', '_1776_', 1).lower()}:latest"


def load_task(path: Path) -> dict:
    task = json.loads(path.read_text())
    missing = [k for k in ("instance_id", "problem_statement") if not task.get(k)]
    if missing:
        raise SystemExit(f"task {path} is missing {', '.join(missing)}")
    return task


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    task = load_task(Path(args.task))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG.read_text())

    import minisweagent
    import yaml
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments.docker import DockerEnvironment
    from minisweagent.models.litellm_model import LitellmModel

    # The prompts come from mini-swe-agent's own SWE-bench config, not from
    # here. Writing our own system and instance templates would change what the
    # agent is while claiming to measure a step-limit change, and the prompt is
    # part of the comparability fingerprint.
    bench = yaml.safe_load(
        (Path(minisweagent.__file__).parent
         / "config/benchmarks/swebench.yaml").read_text())
    agent_config = dict(bench.get("agent", {})) | {
        "step_limit": int(cfg["step_limit"]),
        "mode": cfg.get("mode", "yolo"),
        "confirm_exit": False,
    }

    instance = task["instance_id"]
    image = task.get("image") or image_for(instance)
    started = time.time()
    env = DockerEnvironment(image=image, cwd="/testbed",
                            run_args=["--rm", "--platform=linux/amd64"])
    try:
        agent = DefaultAgent(
            LitellmModel(model_name=cfg["model"],
                         model_kwargs={"drop_params": True}),
            env, **agent_config)
        result = agent.run(task=task["problem_statement"])
        submission = result.get("submission") or ""
        exit_status = str(result.get("exit_status") or "")
    finally:
        env.cleanup()

    (out / "patch.diff").write_text(submission)
    (out / "agent_run.json").write_text(json.dumps({
        "instance_id": instance,
        "image": image,
        "exit_status": exit_status,
        "step_limit": int(cfg["step_limit"]),
        "model": cfg["model"],
        "patch_bytes": len(submission),
        "seconds": round(time.time() - started, 2),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
