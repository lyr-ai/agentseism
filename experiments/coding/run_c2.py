"""Execute the frozen C2 plan, or verify that it could be executed.

Three modes, meant to be run in order:

    --dry-run     expand 72 specs, resolve every archive, print the plan
    --validate    rebuild containers from a sample of fork points, no model
    (default)     run the continuations

Nothing about the plan is a command-line option. Horizons, trajectories and
replication counts come from `c2_protocol.py`, which is the registration turned
into data; a flag that could change them is a flag that eventually would.

**Fail closed.** A fork whose archived source state, workspace fingerprint or
message prefix does not match what was recorded is not run with a warning. It
stops the spec, and `--validate` stops the batch.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import yaml
from minisweagent.agents.interactive import InteractiveAgent

from agents.coding.archiving_agent import archiving
from agents.coding.fork import ForkMismatch, forking, load_step, materialize
from agents.coding.instrumented_model import InstrumentedLitellmModel
from experiments.coding import c2_protocol as P

ForkedAgent = forking(archiving(InteractiveAgent))


def probe_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def resolve(spec: dict, runs: Path) -> dict:
    """Locate the archive for a spec and read back what the fork must reproduce.

    Two archive layouts exist. A Phase A1 run archived as it executed, so its
    probe sits beside the trajectory. A replayed continuation carries its probe
    inside the archive. Both are read here rather than assumed.
    """
    batch, name = spec["source_batch"], spec["source_name"]
    archive = runs / batch / f"{name}.archive"
    step_dir = archive / f"step_{spec['archive_step']:04d}"
    if not step_dir.is_dir():
        raise FileNotFoundError(f"{spec['run_id']}: no archive at {step_dir}")

    inner = archive / "replay.probe.jsonl"
    probe = probe_rows(inner if inner.exists() else runs / batch / f"{name}.probe.jsonl")
    row = next((r for r in probe if r["step"] == spec["archive_step"]), None)
    if row is None:
        raise FileNotFoundError(f"{spec['run_id']}: no probe row for "
                                f"step {spec['archive_step']}")

    final_state = probe[-1]["tracked_diff_hash"]
    archived = load_step(step_dir)
    messages = archived["messages"]
    if not messages:
        raise ForkMismatch(f"{spec['run_id']}: archive has no message prefix")
    if messages[-1].get("role") not in ("tool", "user"):
        raise ForkMismatch(f"{spec['run_id']}: prefix ends on "
                           f"{messages[-1].get('role')}, not an observation")

    return spec | {
        "step_dir": str(step_dir),
        # Declared before any outcome exists. At h=28 five of eight source
        # trajectories are already sitting on their final source state, so a gap
        # between the arms there is partly mechanical -- the answer is already
        # written and the remaining steps verify and submit it. Stratifying on
        # this is the pre-stated way to tell that apart from recoverability.
        "at_source_final": row["tracked_diff_hash"] == final_state,
        "source_total_steps": len(probe),
        "source_final_state": final_state,
        "tracked_diff_hash": row["tracked_diff_hash"],
        "workspace_diff_hash": row["workspace_diff_hash"],
        "prefix_messages": len(messages),
        "prefix_digest": __import__("hashlib").sha256(
            json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16],
    }


def provenance() -> dict:
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                                  text=True, check=True).stdout.strip()
        except Exception:  # noqa: BLE001
            return "unknown"
    return {
        "protocol_hash": P.protocol_hash(),
        "prereg": "paper/PREREG_C2_RECOVERABILITY.md",
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "model": P.MODEL,
        "sampling": P.SAMPLING,
        "serving_config": "inference/configs/model_h2.yaml",
        "image": P.IMAGE,
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def task_text(instance_message: dict) -> str:
    content = instance_message.get("content") or ""
    match = re.search(r"<pr_description>\s*(.*?)\s*</pr_description>", content, re.S)
    return match.group(1) if match else content


def complete(out: Path, run_id: str) -> bool:
    """A result counts only if it terminated, not merely if a file exists.

    The trajectory is written after every step, so a half-finished run leaves a
    perfectly readable file. Resume has to look at the exit status.
    """
    path = out / f"{run_id}.json"
    if not path.exists():
        return False
    try:
        info = json.loads(path.read_text())["info"]
    except Exception:  # noqa: BLE001
        return False
    return bool(str(info.get("exit_status") or ""))


def build_container(spec: dict, out: Path, platform: str):
    probe = out / f"{spec['run_id']}.probe.jsonl"
    probe.unlink(missing_ok=True)
    return materialize(
        Path(spec["step_dir"]), P.IMAGE,
        {"tracked_diff_hash": spec["tracked_diff_hash"],
         "workspace_diff_hash": spec["workspace_diff_hash"]},
        probe_output=str(probe), timeout=120,
        run_args=["--rm"] + ([f"--platform={platform}"] if platform else []),
    )


def run_one(spec: dict, out: Path, platform: str) -> dict:
    env, snapshot = build_container(spec, out, platform)
    prefix = load_step(Path(spec["step_dir"]))["messages"]
    config = yaml.safe_load(
        (Path(__import__("minisweagent").__file__).parent
         / "config/benchmarks/swebench.yaml").read_text())
    agent_config = dict(config.get("agent", {})) | {
        "step_limit": spec["step_limit"], "mode": "yolo", "confirm_exit": False,
        "output_path": str(out / f"{spec['run_id']}.json"),
    }
    agent = ForkedAgent(
        InstrumentedLitellmModel(
            model_name=f"openai/{P.MODEL['id']}", model_kwargs={"drop_params": True},
            stream=True, attempt_timeout=180, max_attempts=6),
        env, prefix_messages=copy.deepcopy(prefix), **agent_config)
    try:
        result = agent.run(task=task_text(prefix[1]))
    finally:
        env.cleanup()
    return {"exit_status": result.get("exit_status"),
            "submission_bytes": len(result.get("submission") or ""),
            "start_tracked": snapshot["tracked_diff_hash"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", default=str(ROOT / "data/runs"))
    ap.add_argument("--out", default=str(ROOT / "data/runs/c2"))
    ap.add_argument("--platform", default="linux/amd64")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--validate", action="store_true",
                    help="rebuild one container per arm × horizon, no model calls")
    args = ap.parse_args()

    runs, out = Path(args.runs), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    specs = [resolve(s, runs) for s in P.expand()]

    # The gate, mechanical rather than documented.
    counts = {arm: sum(1 for s in specs if s["arm"] == arm) for arm in ("FAIL", "PASS")}
    assert counts == {"FAIL": 48, "PASS": 24}, counts
    assert len(specs) == 72

    (out / "plan.json").write_text(json.dumps(
        {"provenance": provenance(), "specs": specs}, indent=1) + "\n")

    print(f"protocol {P.protocol_hash()}   {len(specs)} specs "
          f"({counts['FAIL']} FAIL, {counts['PASS']} PASS)\n")
    at_final = {h: sum(1 for s in specs if s["horizon"] == h and s["at_source_final"])
                for h in P.HORIZONS}
    print("  forks already on the source trajectory's final state, by horizon:")
    for h in P.HORIZONS:
        print(f"    h={h:<3} {at_final[h]:>2} of {sum(1 for s in specs if s['horizon']==h)}"
              f" specs   (declared before any outcome; see prereg amendment C2.1)")
    print()
    print(f"  {'run_id':<34}{'h':>4}{'arch':>6}{'budget':>8}{'prefix':>8}  "
          f"{'tracked':<14}{'final?':<8}{'workspace'}")
    for s in specs:
        print(f"  {s['run_id']:<34}{s['horizon']:>4}{s['archive_step']:>6}"
              f"{s['step_limit']:>8}{s['prefix_messages']:>8}  "
              f"{s['tracked_diff_hash'][:12]:<14}"
              f"{('AT FINAL' if s['at_source_final'] else ''):<8}"
              f"{s['workspace_diff_hash'][:12]}")
    print(f"\nwrote {out}/plan.json")

    if args.dry_run:
        return

    if args.validate:
        print("\n──── zero-LLM fork validation ────")
        sample, seen = [], set()
        for s in specs:
            key = (s["arm"], s["horizon"])
            if key not in seen:
                seen.add(key)
                sample.append(s)
        failures = []
        for s in sample:
            try:
                env, snap = build_container(s, out, args.platform)
                env.cleanup()
                print(f"  {s['run_id']:<34} rebuilt {snap['tracked_diff_hash'][:12]} "
                      f"/ {snap['workspace_diff_hash'][:12]}  ok")
            except ForkMismatch as exc:
                failures.append(f"{s['run_id']}: {exc}")
                print(f"  {s['run_id']:<34} FAIL  {exc}")
        (out / "fork_validation.json").write_text(json.dumps(
            {"provenance": provenance(), "sampled": [s["run_id"] for s in sample],
             "failures": failures}, indent=1) + "\n")
        print(f"\n  {len(sample) - len(failures)}/{len(sample)} rebuilt; "
              f"wrote {out}/fork_validation.json")
        if failures:
            raise SystemExit(1)
        return

    for s in specs:
        if complete(out, s["run_id"]):
            print(f"skip  {s['run_id']}", flush=True)
            continue
        t0 = time.time()
        try:
            row = run_one(s, out, args.platform)
            print(f"{s['run_id']:<34} {time.time()-t0:6.0f}s  {row['exit_status']}  "
                  f"{row['submission_bytes']} B", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{s['run_id']:<34} {time.time()-t0:6.0f}s  FAILED  "
                  f"{type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
