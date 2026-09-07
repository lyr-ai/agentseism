# Pre-registration — coding-agent divergence experiment

Written before any multi-task coding run. Frozen inputs: `coding/1`
(`agents/coding/`), `mini-swe-agent` 2.4.6, `Qwen/Qwen3.6-27B-FP8` at revision
`e89b16ebf1988b3d6befa7de50abc2d76f26eb09` served by vLLM 0.28.0, temperature 0.

## Hypothesis

> **H.** The fate of stochastic execution variation depends on the task's
> solution landscape. Some tasks absorb divergent execution through
> reconvergence; others let divergence persist into distinct final patches.

The claim under test is that this differs **between tasks**, not that either
behaviour dominates. A finding that all five tasks absorb is a result, and so is
a finding that none do.

## Tasks

SWE-bench Verified, in dataset order, the first five instances. No selection on
difficulty, repository, or observed behaviour. `astropy__astropy-12907` is
instance 0 and stays in, despite having been used for qualification: dropping it
would be selection on a seen outcome, and its qualification runs are not reused
as data.

**3 runs per task, 15 runs.** Three gives three pairs per task, enough to ask
whether paths differ and whether they end together, and not enough to estimate
anything. At ~12.2 minutes per run this is ~3 hours and ~$1.50 on one A40.

## The three quantities

Measured from `coding/1` artefacts only — command signatures and repository
fingerprints. No reasoning text, no semantic labels.

Sparsity forced the levels apart. In the instrumented runs the source state moved
12 times for Sonnet over 41 actions and **once** for Qwen over 20: Qwen wrote the
fix nearly in one shot. Defining everything on source state would make every pair
of Qwen runs trivially reconvergent, since their whole trajectory is "empty ->
final patch". So divergence is measured where the resolution exists, and
reconvergence where it means something.

**Divergence — action level.** For a pair of runs, the first index at which their
command-signature sequences differ. `None` if identical throughout.

**Reconvergence — state level.** After the divergence index, whether the two runs
ever hold the same `tracked_diff_hash` at any subsequent step. Measured on source
state, because two runs that briefly wrote different scratch files have not
meaningfully reconverged in the repository.

**Persistence — outcome level.** Whether the final `tracked_diff_hash` differs.
Reported alongside the exact patch bytes, since identical hashes and identical
patches should agree and a disagreement is a bug.

Also recorded, not part of H: `workspace_diff_hash` transitions, action count,
reasoning-token share, wall clock.

## What supports and what refutes

Per task, over three pairs, each pair is classified:

| | diverged | reconverged | same final patch |
|---|---|---|---|
| absorbed | yes | yes | yes |
| persistent | yes | no | no |
| identical | no | -- | yes |
| **anomalous** | yes | yes | **no** |
| **anomalous** | yes | no | **yes** |

**Supports H:** at least one task where all pairs are absorbed and at least one
where any pair is persistent. That is the heterogeneity the hypothesis is about.

**Refutes H, informatively:** every pair on every task absorbed. Coding tasks
would then have strong solution attractors and the interesting question becomes
absorption itself, not its variation.

**Refutes H, awkwardly:** no two runs ever reconverge and every task persists.
Then reconvergence is not a property this representation can see, and the
discrete-state formulation needs revisiting before more data.

**Anomalous rows are a measurement problem, not a finding.** Reconverging and
then ending with different patches means the state sequence lost something, and
the response is to fix the instrumentation, not to interpret the row.

## Fixed in advance

- No task is added, dropped, or rerun after seeing its classification.
- Fifteen runs, whatever the counts look like at run 12.
- `coding/1` is not extended mid-experiment. Adding reasoning text or semantic
  labels to rescue a null means `coding/2` and a written reason.
- Cost is wall-clock, not token-priced: `instance_cost` is unavailable for a
  self-hosted model and litellm's price table does not know it, so
  `MSWEA_COST_TRACKING=ignore_errors` is set and GPU-hours are recorded instead.
- A run that fails for infrastructure reasons — endpoint down, container
  failure — is rerun and both attempts recorded. A run the agent itself ends
  without a patch is data and stays.

---

## Amendment, 2026-09-07 — repository confound in the selection rule

**No trajectory outcome from the primary experiment had been observed when this
was written.** The amendment rests on task metadata alone: applying the original
rule and reading the repository field of the five instances it returned.

The original rule — SWE-bench Verified in dataset order, first five instances —
yields five tasks from one repository:

    astropy__astropy-12907 / -13033 / -13236 / -13398 / -13453

The hypothesis concerns cross-task differences in solution landscapes. Five
instances of one project share its code structure, test framework and repair
idioms, so repository identity would be structurally confounded with the task
set: had all five absorbed, "coding tasks absorb divergence" and "this project's
issues absorb divergence" would be indistinguishable. The defect is in the
sampling frame, and it is visible before any run.

### Replacement rule, equally deterministic

Traverse the dataset in its original fixed order; take the first instance of each
repository not yet represented; stop at five repositories. Eligibility is
otherwise unchanged.

    idx    0   astropy__astropy-12907          astropy/astropy
    idx   22   django__django-10097            django/django
    idx  253   matplotlib__matplotlib-13989    matplotlib/matplotlib
    idx  287   mwaskom__seaborn-3069           mwaskom/seaborn
    idx  289   pallets__flask-5014             pallets/flask

No repository was chosen for being interesting, and no instance was swapped for
difficulty or for how the model handled it. `astropy__astropy-12907` remains
first under both rules.

Everything else in this document stands: three runs per task, `coding/1`
unchanged, the three quantities and their levels, the support and refutation
conditions, and the two classifications declared to be measurement bugs.

The original rule is left in place above rather than edited, so that what
changed, when, and on what evidence is recoverable.
