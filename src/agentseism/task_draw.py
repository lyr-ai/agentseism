"""Execute the registered task draw (amendment P.3).

The rule lives in `pilot_protocol.select_tasks` and is pure. This module is the
only thing that touches Docker: it fetches one image per candidate the rule
asks about, writes every examined candidate to a TSV with the reason it was
skipped, and writes the drawn ids.

There is no retry. A pull is issued once, and a failure is a recorded fact
about that candidate rather than something to attempt until it succeeds --
otherwise a flaky registry would quietly reshape the draw.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agentseism import pilot_protocol as P  # noqa: E402

REGISTRY = "docker.io/swebench/sweb.eval.x86_64"


def image_for(instance_id: str) -> str:
    """The official SWE-bench image name. `__` becomes `_1776_`, once, exactly
    as `inference/eligibility.sh` has always built it."""
    return f"{REGISTRY}.{instance_id.replace('__', '_1776_', 1).lower()}:latest"


class DiskExhausted(RuntimeError):
    """Stop before filling the disk, rather than after."""


def docker_pull(instance_id: str, min_disk_gb: int, timeout: int = 3600) -> bool:
    free_gb = shutil.disk_usage("/").free // (1000 ** 3)
    if free_gb < min_disk_gb:
        raise DiskExhausted(
            f"{free_gb} GB free before pulling {instance_id}; stopping rather "
            f"than filling the disk (want >= {min_disk_gb} GB)")
    r = subprocess.run(
        ["docker", "pull", "--platform", "linux/amd64", "--quiet",
         image_for(instance_id)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    return r.returncode == 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--universe", required=True,
                    help="candidate instance ids, one per line, already sorted")
    ap.add_argument("--tsv", required=True, help="every candidate examined")
    ap.add_argument("--drawn", required=True, help="the drawn ids")
    ap.add_argument("--min-disk-gb", type=int, default=100)
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve the draw with every pull assumed to succeed; "
                         "writes nothing and fetches nothing")
    args = ap.parse_args(argv)

    candidates = [l.strip() for l in Path(args.universe).read_text().splitlines()
                  if l.strip()]
    if not candidates:
        print("the candidate universe is empty", file=sys.stderr)
        return 2

    if args.dry_run:
        drawn, rows = P.select_tasks(candidates, lambda _: True)
        for iid in drawn:
            print(f"  would draw  {iid:<34} {P.repository_of(iid)}")
        return 0

    rows_out: list[tuple[str, str, str, str]] = []

    def pull(instance_id: str) -> bool:
        got = docker_pull(instance_id, args.min_disk_gb)
        rows_out.append((instance_id, image_for(instance_id),
                         "pulled" if got else "-", ""))
        return got

    try:
        drawn, rows = P.select_tasks(candidates, pull)
    except (P.ProtocolMismatch, DiskExhausted, ValueError) as e:
        # Everything examined is still written: the record of a draw that
        # failed is worth as much as the record of one that succeeded.
        _write(args, [], rows_out, partial=str(e))
        print(f"task draw failed: {e}", file=sys.stderr)
        return 1

    _write(args, drawn, rows_out, rows=rows)
    for iid in drawn:
        print(f"  drawn  {iid:<34} {P.repository_of(iid)}")
    repos = {P.repository_of(i) for i in drawn}
    print(f"  {len(drawn)} tasks across {len(repos)} repositories; "
          f"{len(rows_out)} pulls attempted")
    return 0


def _write(args, drawn, pulls, rows=None, partial: str = "") -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    pulled = {iid for iid, _, res, _ in pulls if res == "pulled"}
    lines = ["instance\trepository\timage\tresult\tutc"]
    for iid, reason in (rows or []):
        lines.append("\t".join([
            iid, P.repository_of(iid),
            image_for(iid) if iid in pulled or reason == "pull_failed" else "-",
            reason, ts]))
    if partial:
        lines.append(f"#\t-\t-\tdraw_failed: {partial}\t{ts}")
    Path(args.tsv).write_text("\n".join(lines) + "\n")
    Path(args.drawn).write_text("".join(f"{i}\n" for i in drawn))


if __name__ == "__main__":
    raise SystemExit(main())
