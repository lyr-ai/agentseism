# Run data

Trajectories and probe records from the coding experiments. Moved here from a
scratch directory on 2026-09-12, **after a temp cleaner had already deleted part
of it**.

## What was lost

    exp1/         the primary 30-run experiment — 10 tasks × 3 runs.  GONE.
    h2_phase_a/   batch A0, 5 pytest runs.                            GONE.

Both directories survive with zero files: the cleaner removed files by age and
left the directory tree, which is why the loss was not obvious until the data
was needed. Everything derived from them is still in `paper/` — the topology
counts, the gate reports, the manifests, the figures' inputs — but the raw
trajectories cannot be regenerated. A rerun would be different runs.

## What survives

    h2_phase_a1/        5 pytest runs, Submitted, with step archives
    h2_phase_b/         16 continuations (8 arm A, 8 arm B; B_1 incomplete)
    *_aborted, *_hung   infrastructure-failed batches, kept as recorded

## The second bite

The same cleaner also gutted the mini-swe-agent checkout and its virtualenv that
every script depended on — `src/minisweagent/` survives as empty directories,
`config/benchmarks/swebench.yaml` is gone, and the venv's site-packages with it.

The fix was not to rescue it again. `.venv-eval/` in this repository now holds
`mini-swe-agent==2.4.6` and `swebench==5.0.2` installed from PyPI, so nothing
the analysis needs lives in a temp directory any more. Scripts take paths to it
rather than to a scratch checkout.

## What is in git

`*.json` trajectories and `*.probe.jsonl` probe records — 14 MB, textual,
irreplaceable.

`*.archive/` step archives are **not** in git: 86 MB of tar and diff blobs. They
are what makes forking possible, so if Phase B is ever re-run from these donors
they must still exist locally. They are not durable here and that is a known
risk, accepted rather than overlooked.
