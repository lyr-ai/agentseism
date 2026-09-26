"""Eligibility for the coding experiment, using the benchmark's own test command.

An earlier version ran `pytest --collect-only` in every container and called
django and scikit-learn ineligible. Django does not use pytest -- SWE-bench
invokes `./tests/runtests.py` for it -- so the checker was asserting a framework
rather than measuring an environment.

The command now comes from `MAP_REPO_VERSION_TO_SPECS`, which is SWE-bench's own
per-repository mapping, and the tests run are the instance's own `PASS_TO_PASS`
list: tests the benchmark states pass both before and after the gold patch. If
those pass at the base commit, the environment is valid for this instance, which
is exactly what the gate needs to establish.

No model is invoked, so eligibility cannot depend on agent behaviour.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DOCKER = "docker"
BASELINE_TESTS = 5
"""Enough to prove the harness runs. The full suite can take many minutes per
repository, and a valid baseline does not require all of it."""


def image_for(instance_id: str) -> str:
    return ("docker.io/swebench/sweb.eval.x86_64."
            + instance_id.replace("__", "_1776_").lower() + ":latest")


def run(image: str, script: str, timeout: int = 900) -> tuple[int, str]:
    p = subprocess.run(
        [DOCKER, "run", "--rm", "--platform", "linux/amd64", image, "bash", "-lc", script],
        capture_output=True, text=True, timeout=timeout,
    )
    return p.returncode, (p.stdout + p.stderr)


def check(instance: dict, test_cmd: str) -> dict:
    iid = instance["instance_id"]
    image = image_for(iid)
    tests = json.loads(instance["PASS_TO_PASS"] or "[]")[:BASELINE_TESTS]
    quoted = " ".join(f'"{t}"' for t in tests)

    script = f"""
source /opt/miniconda3/bin/activate 2>/dev/null && conda activate testbed 2>/dev/null
cd /testbed || {{ echo 'NO_TESTBED'; exit 1; }}
echo "DIRTY=$(git status --porcelain | wc -l | tr -d ' ')"
echo '---TESTS---'
{test_cmd} {quoted} 2>&1 | tail -25
"""
    code, out = run(image, script)
    dirty = re.search(r"DIRTY=(\d+)", out)
    clean = bool(dirty) and dirty.group(1) == "0"

    # Accept either framework's summary. Never parse by line position: astropy
    # prints "Interrupted" after a successful collection of 21999 tests, and
    # reading the last line called that a failure.
    passed = bool(re.search(r"\b(\d+ passed|OK|Ran \d+ tests? in)\b", out))
    failed = bool(re.search(r"\b(\d+ (failed|error)|FAILED \(|ERROR:)\b", out))
    ok = passed and not failed

    return {
        "instance_id": iid,
        "repo": instance["repo"],
        "test_cmd": test_cmd,
        "baseline_tests": len(tests),
        "clean_tree": clean,
        "tests_pass": ok,
        "eligible": clean and ok,
        "tail": out[-400:] if not (clean and ok) else "",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", default="/tmp/swe10.txt")
    ap.add_argument("--test-cmds", default="/tmp/test_cmds.json")
    ap.add_argument("--out", default="/tmp/eligibility.json")
    args = ap.parse_args()

    from datasets import load_dataset
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    by = {r["instance_id"]: dict(r) for r in ds}
    cmds = json.loads(Path(args.test_cmds).read_text())
    ids = [x.strip() for x in Path(args.instances).read_text().split() if x.strip()]

    rows = []
    for iid in ids:
        inst = by[iid]
        cmd = cmds.get(inst["repo"])
        if not cmd:
            print(f"{iid:<34} NO TEST COMMAND for {inst['repo']}")
            continue
        try:
            r = check(inst, cmd)
        except subprocess.TimeoutExpired:
            r = {"instance_id": iid, "repo": inst["repo"], "eligible": False,
                 "clean_tree": None, "tests_pass": False, "tail": "TIMEOUT"}
        rows.append(r)
        print(f"{iid:<34} {'ELIGIBLE' if r['eligible'] else 'INELIGIBLE':<11}"
              f"clean={r['clean_tree']} tests={r['tests_pass']}")
        if not r["eligible"] and r.get("tail"):
            print("    " + r["tail"].replace("\n", " ")[-160:])

    Path(args.out).write_text(json.dumps(rows, indent=2))
    n = sum(r["eligible"] for r in rows)
    print(f"\n{n} eligible of {len(rows)}  ->  {args.out}")
    sys.exit(0)


if __name__ == "__main__":
    main()
