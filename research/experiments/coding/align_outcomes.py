"""Exploratory C1 — time-aligned comparison of passing and failing runs.

**Post-hoc throughout, on four failures.** Nothing here is a finding. The output
is a list of candidate signals and a candidate horizon, to be fixed in advance
and tested on a batch that does not include these runs. Any feature that looks
convincing on 16 against 4 will look convincing on noise.

Two alignments, because they answer different questions:

    absolute step    when in wall-clock terms does a difference appear
    fraction of run  is the difference positional rather than temporal

Everything is reported with the denominator at each horizon, because runs are
23 to 70 steps long and late horizons are a handful of survivors.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.coding.step_features import features, load, observations

def load_joined(runs_dir: str, donor_batch: str, donor_name: str, fork: int,
                cont_batch: str, cont_name: str) -> list[dict]:
    donor_base = Path(runs_dir) / donor_batch / donor_name
    cont_base = Path(runs_dir) / cont_batch / cont_name
    donor_probe = [json.loads(l) for l in open(f"{donor_base}.probe.jsonl")][:fork]
    cont_probe = [json.loads(l) for l in open(f"{cont_base}.probe.jsonl")]
    donor_obs = observations(json.loads(Path(f"{donor_base}.json").read_text()))
    cont_obs = observations(json.loads(Path(f"{cont_base}.json").read_text()))
    merged = {k: v for k, v in donor_obs.items() if k <= fork}
    merged.update({k + fork: v for k, v in cont_obs.items()})
    fake = {"messages": []}
    rows = features(donor_probe + cont_probe, fake)
    # `features` reads observations from the trajectory; supply the merged map
    # by recomputing the two observation-dependent fields directly.
    import re as _re
    from experiments.coding.step_features import TEST_RE, FAILED_RE
    failing = 0
    for row, probe in zip(rows, donor_probe + cont_probe):
        text = merged.get(row["step"], "")
        row["test_failed"] = bool(TEST_RE.search(probe.get("command", "") or "")) and \
            bool(FAILED_RE.search(text))
        failing += row["test_failed"]
        row["cum_failing_tests"] = failing
    return rows


CUMULATIVE = ["cum_edits", "cum_tests", "cum_suite_tests", "cum_reverts",
              "cum_failing_tests", "distinct_states", "diff_bytes",
              "steps_since_source_change"]


def gather(runs_dir: str, labels: list[dict], manifest: dict) -> list[dict]:
    """Absolute-step feature sequences, with the donor prefix prepended.

    A continuation restarts the environment's step counter at 1, but its first
    step is absolutely step 9 or 11 — it inherited everything before that from
    its donor. Aligning continuation step 1 with a fresh run's step 1 compares
    a run that has already made two edits with one that has made none.

    So the donor's probe rows are prepended and the features recomputed over the
    join, which gives both the right horizon index and cumulative counters that
    carry the inherited work.
    """
    out = []
    for row in labels:
        correct = row["resolved"]
        if row["batch"] == "b":
            arm = row["run"].split("_")[0]
            donor = manifest["arms"][arm]
            fork = donor["fork_step"]
            base = f"pytest-dev__pytest-10051__r{donor['run']}"
            try:
                steps = load_joined(runs_dir, "h2_phase_a1", base, fork,
                                    "h2_phase_b", row["run"])
            except FileNotFoundError:
                continue
            out.append({"run": row["run"], "batch": row["batch"], "arm": arm,
                        "fork": fork, "correct": correct, "steps": steps})
        else:
            name = f"pytest-dev__pytest-10051__{row['run']}"
            try:
                steps = load(runs_dir, "h2_phase_a1", name)
            except FileNotFoundError:
                continue
            out.append({"run": row["run"], "batch": row["batch"], "arm": None,
                        "fork": 0, "correct": correct, "steps": steps})
    return out


def cohen_d(good: list[float], bad: list[float]) -> float | None:
    if len(good) < 2 or len(bad) < 2:
        return None
    pooled = (((len(good) - 1) * statistics.pvariance(good)
               + (len(bad) - 1) * statistics.pvariance(bad))
              / (len(good) + len(bad) - 2)) ** 0.5
    return None if pooled == 0 else (statistics.mean(bad) - statistics.mean(good)) / pooled


def compare(runs: list[dict], key: str, horizons: range) -> list[dict]:
    """Means, difference and standardised effect at each horizon.

    Reporting the *sign* of the difference was the mistake this function now
    exists to prevent. A column of minus signs reads as separation and can be
    3.12 against 3.00 — which is what h=14 actually was, and a pre-registration
    was nearly written around it.
    """
    rows = []
    for h in horizons:
        good = [r["steps"][h - 1][key] for r in runs if r["correct"] and len(r["steps"]) >= h]
        bad = [r["steps"][h - 1][key] for r in runs if not r["correct"] and len(r["steps"]) >= h]
        if len(good) < 2 or len(bad) < 2:
            continue
        rows.append({"h": h, "n_pass": len(good), "n_fail": len(bad),
                     "pass_mean": statistics.mean(good), "fail_mean": statistics.mean(bad),
                     "delta": statistics.mean(bad) - statistics.mean(good),
                     "cohen_d": cohen_d(good, bad)})
    return rows


def independent_histories(runs: list[dict], h: int) -> int:
    """How many genuinely distinct trajectories exist at this horizon.

    Continuations in an arm are byte-identical before their fork step, so twenty
    runs at h=8 are seven trajectories. Reported next to every effect size
    because an effect computed over pseudo-replicates is not an effect, and the
    first version of this analysis published one.
    """
    keys = set()
    for r in runs:
        if len(r["steps"]) < h:
            continue
        keys.add((r["arm"], "prefix") if r["arm"] and h <= r["fork"] else (r["run"],))
    return len(keys)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    labels = json.loads(Path(args.labels).read_text())["rows"]
    manifest = json.loads(Path(args.manifest).read_text())
    runs = gather(args.runs, labels, manifest)
    good = [r for r in runs if r["correct"]]
    bad = [r for r in runs if not r["correct"]]
    print(f"{len(good)} pass, {len(bad)} fail, lengths "
          f"{min(len(r['steps']) for r in runs)}–{max(len(r['steps']) for r in runs)}\n")

    print("── run lengths ──")
    for group, label in ((good, "PASS"), (bad, "FAIL")):
        lengths = sorted(len(r["steps"]) for r in group)
        print(f"  {label}  n={len(group):>2}  median {statistics.median(lengths):>4.0f}  {lengths}")

    print("\n── totals at end of run ──")
    print(f"  {'feature':<26}{'PASS mean':>11}{'FAIL mean':>11}{'delta':>9}")
    for key in CUMULATIVE:
        g = [r["steps"][-1][key] for r in good]
        b = [r["steps"][-1][key] for r in bad]
        print(f"  {key:<26}{statistics.mean(g):>11.1f}{statistics.mean(b):>11.1f}"
              f"{statistics.mean(b)-statistics.mean(g):>+9.1f}")

    print("\n── effective independence at each horizon ──")
    print("  Before its fork step every continuation in an arm has the *same*")
    print("  history, so early horizons are pseudo-replicated:")
    for h in (5, 8, 10, 12, 15, 20):
        alive = [r for r in runs if len(r["steps"]) >= h]
        distinct = {(r["arm"], min(h, r["fork"])) if r["arm"] and h <= r["fork"]
                    else (r["run"],) for r in alive}
        print(f"    h={h:<3} runs at risk {len(alive):>2}   distinct histories {len(distinct):>2}")

    print("\n── effect size by horizon (Cohen's d, FAIL − PASS) ──")
    print("  Magnitudes, not signs. |d| < 0.2 is nothing whatever the sign says.")
    print("  n_P / n_F are runs still alive at the horizon — late rows are survivors.")
    print("  ind is distinct histories: an effect over pseudo-replicates is not an effect.\n")
    results = {}
    keys = ["cum_edits", "diff_bytes", "distinct_states", "cum_reverts", "cum_tests"]
    print(f"  {'h':>3}{'n_P':>5}{'n_F':>4}{'ind':>5}  " + "".join(f"{k:>17}" for k in keys))
    for h in range(8, 45, 2):
        series = {k: compare(runs, k, range(h, h + 1)) for k in keys}
        if not series["cum_edits"]:
            break
        first = series["cum_edits"][0]
        cells = []
        for k in keys:
            row = series[k][0] if series[k] else None
            d = row and row["cohen_d"]
            cells.append(f"{row['pass_mean']:5.0f}/{row['fail_mean']:<5.0f}"
                         + ("  —  " if d is None else f"{d:+5.2f}") if row else "")
        print(f"  {h:>3}{first['n_pass']:>5}{first['n_fail']:>4}"
              f"{independent_histories(runs, h):>5}  "
              + "".join(f"{c:>17}" for c in cells))
    for key in CUMULATIVE:
        results[key] = compare(runs, key, range(1, 45))

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"exploratory": True, "post_hoc": True,
             "n_pass": len(good), "n_fail": len(bad), "by_feature": results}, indent=1) + "\n")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
