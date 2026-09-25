# Product mainline recovery — audit

Audit only. No code changed, nothing merged, nothing deleted, no experiment run.
Verified against implementation and tests, not against design documents.

2026-09-25. Branch `eval/pilot-outcome-grounded-ci` @ `56ea5fe`, `master` @
`2ff84bb`.

---

## Task 1 — the authoritative mainline

`README.md` already leads with the product question and needs no change. The
conflict is that **four documents still read as the active plan** while
describing the superseded research programme, and a contributor arriving at the
repository root meets them first.

| document | lines | presents itself as | conflict |
|---|---|---|---|
| `DESIGN.md` | 1076 | "V0 Design Doc… Primary goal: Research prototype" | **highest risk.** Root-level, largest design doc, one-line description is weak-point discovery. Nothing marks it superseded |
| `ROADMAP.md` | 98 | "Six weeks, four decision points" with live checkboxes | **highest risk.** Root-level, reads as the current plan; it is the GAIA/Figure-1 research schedule |
| `DESIGN-FEATURE-PROJECTION.md` | 523 | "Design Draft v0.2 … V0 alignment and attribution model" | root-level, no status marker |
| `DESIGN-INTERVENTION.md` | 169 | "Design Draft v0.3 · contract only" | already says not implemented; lower risk |
| `docs/DESIGN-ci-stochastic-regression.md` | 580 | carries an explicit "superseded as the research main line" banner | **correctly handled** — the model to copy |
| `docs/DESIGN-regression-testing-mainline.md` | 161 | "Direction, decided 2026-09-20" | authoritative, but buried in `docs/` |
| `docs/DECISION-product-first.md` | 89 | decision record | authoritative |
| `docs/CONVERGENCE.md` | 83 | explains the shift | authoritative |
| `docs/ROADMAP-2026-09-20.md` | 365 | the newer roadmap | competes with root `ROADMAP.md` by filename alone |

### Minimum change proposed

Four edits. No deletions, no rewrites.

1. **`DESIGN.md`** — add a banner in the style `DESIGN-ci-stochastic-regression.md`
   already uses: superseded as the project plan, retained as the V0 research
   design, pointer to `docs/DESIGN-regression-testing-mainline.md`.
2. **`ROADMAP.md`** — same banner, plus a first line pointing at
   `docs/ROADMAP-2026-09-20.md`. Its checkboxes are the single most misleading
   artefact in the repository: they look like open work.
3. **`DESIGN-FEATURE-PROJECTION.md`** — one-line status marker.
4. **`README.md`** — one "Where the plan lives" line naming the three
   authoritative documents, so the entry point resolves the ambiguity rather
   than leaving a reader to compare timestamps.

That is sufficient: every remaining research document is either already marked
or reachable only from a marked one.

---

## Task 2 — recent branches

One branch diverges from `master`: `eval/pilot-outcome-grounded-ci`, **80
commits**, all ahead. `master` has nothing the branch lacks. No other local or
remote branches exist.

The 80 commits are dominated by one activity — building and running a
pre-registered GPU pilot that produced **zero experimental cells**. Classified
by function rather than by chronology:

| group | commits | classification | reason |
|---|---|---|---|
| Pre-registration documents and amendments P.2–P.10, F3 prereg | ~14 | **RESEARCH-ONLY** | experimental protocol machinery; must remain available, must not shape product architecture |
| Budget state machine: baseline freeze, readings, `not_before`, supersession, `--observe`, per-host guard, cost projection | ~12 | **CHERRY-PICK** | genuinely generic cost control, but entangled with pilot vocabulary (`pilot_spend`, checkpoints). Useful to the product; not mergeable wholesale |
| `stage_b_preflight.sh` + its 126-assertion mock harness | ~15 | **RESEARCH-ONLY** | GPU host bring-up. No product path touches it |
| Pilot/F3/engineering protocol modules and the CLI that runs them (`pilot.py`, `pilot_protocol.py`, `f3_protocol.py`, `engineering_protocol.py`, `protocol_spec.py`) | ~10 | **RESEARCH-ONLY** | a second runner parallel to the product CLI, with its own identity and budget model |
| `real_backend.py`, `smoke.py`, evaluator-report preservation, digest verification | ~8 | **CHERRY-PICK** | artifact/provenance handling is product-relevant; the surrounding protocol is not |
| Host records, closure records, postmortem, failure matrix, final reviews | ~12 | **RESEARCH-ONLY** | evidence of what happened; keep, do not build on |
| Docker probes, `_docker_guard`, timeouts, container cleanup | ~4 | **CHERRY-PICK** | generic test-infrastructure hardening |
| Engineering-namespace records, `probe_only`, deployment-path closure | ~5 | **RESEARCH-ONLY** | explicitly `experimental_evidence: false`; historical |

**No commits classify as MERGE.** Nothing on this branch is generic product
functionality required by stochastic-agent CI. The product path — `cli.py`,
`contract.py`, `resolve.py`, `pr_report.py`, `runner/`, `execution.py` — is
already on `master` and was not the subject of these 80 commits.

**No commits classify as DROP** either, on a narrower reading than the task
allows: the deployment-specific material is the evidentiary record of a closed
experiment, and the constraint says not to delete research artifacts. If DROP
is meant as "exclude from any product branch", then the whole
`inference/stage_b_preflight.sh` group qualifies.

### The specific question: `56ea5fe`

That SHA is the closure record. The two commits that matter are `d682169` and
`b54951f`, the PYTHONPATH fix and its regression test.

**The test is generic and worth keeping. The fix is not.**

- `PYTHONPATH="$REPO/src:$REPO"` patches one line of
  `inference/stage_b_preflight.sh`, a script that exists only to bring up a GPU
  host for a closed experiment. It has no product reachability.
- The *test* — `test_the_smoke_marker_imports_from_outside_the_repo` — runs a
  script's declared imports from a directory that is not the repository, using
  the PYTHONPATH parsed out of the script itself. Its value is the general
  lesson, which the commit message records: **the 126-assertion harness passed
  with the bug present**, because its mock replaced the failing module and
  every other test ran with the repo as cwd. That is a reusable technique for
  any shell/Python boundary the product later grows, and it currently applies
  to nothing in the product.

Recommendation: retain both where they are (the test is worthless without the
script it parses), and record the technique in `INVARIANTS.md`, which already
exists for exactly this kind of "an analysis reported something untrue" lesson.
Do not port either to the product branch now.

---

## Task 3 — the product vertical slice

Verified by reading `src/agentseism/cli.py`, `contract.py`, `resolve.py`,
`pr_report.py`, `runner/`, and running `tests/test_cli.py test_contract.py
test_resolve.py test_runner.py` — **130 passed**.

| stage | status | evidence |
|---|---|---|
| install | **WORKING** | package + `seism` console entry |
| configure | **WORKING** | `seism init` scaffolds `.agentseism/contract.yaml`, `tasks.yaml`, `baselines/`, `runs/`; never overwrites |
| baseline | **WORKING** | `seism baseline --trials N`, frozen to `baselines/<name>.json` with a fingerprint |
| candidate | **WORKING** | `seism check --baseline main --trials N` |
| repeated trials | **WORKING** | `run_trials(...)` over tasks × trials; per-trial progress; invalid runs tracked separately |
| measurement | **WORKING** | paired bootstrap over **tasks**, not runs; features absent from the runs are omitted rather than defaulted to zero |
| verdict | **WORKING** | all five verdicts implemented and reachable |
| PR report | **PARTIAL** | renders markdown + JSON to `runs/last-report.{md,json}`; **nothing posts it to a pull request** |
| RCA / localization | **MISSING** | `cmd_diagnose` is a four-line stub; `localization/` is referenced by the CLI **zero** times |

### The nine questions

1. **Arbitrary external agent without modifying internals — YES.**
   `runner: {type: shell, command: "..."}` or `{type: python, callable:
   "mod:fn"}`. Tests exercise both, including an unimportable callable failing
   before trial zero.
2. **User-supplied deterministic evaluator — YES.** `evaluator: {command: ...}`
   via `ShellEvaluator`, with its own timeout.
3. **Repeated baseline and candidate trials — YES.** `--trials` on both.
4. **Stochastic variation vs material regression — YES.** Paired bootstrap CI
   over tasks, with per-feature thresholds and a minimum-evidence rule; a
   feature below minimum evidence becomes `INSUFFICIENT_EVIDENCE` rather than
   a pass.
5. **All five verdicts — YES.** `VERDICTS = (INCOMPARABLE, REGRESSION,
   INSUFFICIENT_EVIDENCE, PASS_WITH_CHANGE, PASS)`, each returned by `decide`,
   and tests assert `REGRESSION`, `INCOMPARABLE`, `INSUFFICIENT_EVIDENCE` and
   `PASS` through `main([...])` end to end.
6. **Verdicts from declared outcome evidence only — YES, enforced.** The
   contract validator rejects a configuration where a non-outcome feature could
   raise `REGRESSION`, where `rca.run_only_when != REGRESSION`, where
   `comparability.mismatch_verdict != INCOMPARABLE`, or where no feature gates
   at all. A diagnostic that moves yields `PASS_WITH_CHANGE`, never a block.
7. **RCA only after a regression — ENFORCED IN CONTRACT, ABSENT IN CODE.**
   `decide` sets `rca: True` only on `REGRESSION`, but no RCA runs: `seism
   diagnose` prints a sentence and exits 0.
8. **Machine-readable CI result — YES.** `runs/last-report.json` carries
   verdict, per-feature detail and provenance; `seism check` exits 1 on
   `REGRESSION` and on `INCOMPARABLE`, 0 otherwise.
9. **What prevents use on a real PR today — three things.**
   - **No GitHub Action.** `.github/workflows/` does not exist. The report is a
     file; getting it onto a pull request is manual.
   - **Never run against a real agent.** Every test uses local stub scripts. No
     execution against a real model-calling agent has happened through this
     path — which is precisely the failure mode the pilot postmortem named.
   - **No cost signal.** `_plan` states outright that cost is not estimated.
     Acceptable, but a developer cannot predict the spend of `--trials 5`.

**RESEARCH-COUPLED:** none of the nine stages. The product path imports nothing
from `pilot*.py`, `*_protocol.py`, `smoke.py` or `real_backend.py`. The two
code bases are already separate; the coupling is in the documentation, not the
imports.

---

## Task 4 — the single next milestone

### Milestone: one real agent change, end to end, producing a CI verdict

> A real baseline/candidate change to an external, model-calling agent goes
> through `seism baseline` → `seism check`, with repeated stochastic trials,
> and AgentSeism emits an evidence-grounded verdict and a report a developer
> would act on.

**Exact missing implementation** — one item:

- A GitHub Action that runs `seism check` on a pull request and posts
  `runs/last-report.md` as a sticky comment, failing the check on exit 1.
  Roughly one workflow file plus a small posting step. Nothing else in the
  vertical slice is missing.

`seism diagnose` is **explicitly out of scope**: the milestone is the merge
decision, and localization is diagnostic by the product's own rule.

**Existing components reused, unchanged:** `cli.py` (`init`/`baseline`/`check`),
`contract.py` (`decide`, `precheck_comparability`, validation),
`resolve.py`, `pr_report.py` (`render`, `as_json`), `runner/`,
`execution.py` (fingerprint, runtime identity), the `ShellRunner`/
`ShellEvaluator` pair, and `contracts/default.yaml`.

**The change to exercise it.** Use an agent already adapted in this repository
and make a change whose direction is known in advance — a prompt or step-limit
edit expected to hurt. Two candidates already exist: `agents/gaia_markazhang.py`
(a real LangGraph GAIA agent with a runbook) and the coding agent under
`agents/coding/`. Prefer whichever is cheapest to invoke; the milestone is
about the pipeline, not the agent.

**Runs.** 5 tasks × 5 trials × 2 arms = **50 agent invocations**. Enough for the
paired bootstrap to have 5 independent units, which is the minimum the
measurement treats as a unit.

**Approximate cost.** At a few cents per invocation for a small multi-step
agent, **on the order of $5–15**. No GPU, no rented host. If the chosen agent
is more expensive than that, cut to 3 tasks before cutting trials — trials are
what separate stochastic variation from a regression.

**Acceptance criteria** — product value, not execution:

1. The baseline run produces a frozen baseline with a fingerprint, and a second
   baseline run on unchanged code yields **PASS**, not a regression. *Without
   this the tool reports its own noise as a finding.*
2. The deliberately worse candidate yields **REGRESSION**, with the report
   naming the regressed feature, the effect and its interval.
3. The report is posted on a real pull request and the check goes red.
4. A reader who did not run it can tell from the comment alone **whether to
   merge**, and which feature moved.
5. An environment change between arms yields **INCOMPARABLE** with zero
   candidate trials executed.

**Criteria 1 and 2 are a pair and neither counts alone.** Criterion 1 is a
false-positive control: it shows AgentSeism does not report its own stochastic
noise as a regression. Criterion 2 is the false-negative control. A tool that
returned PASS unconditionally would satisfy criterion 1 perfectly, so passing it
in isolation demonstrates nothing — the pair is specificity and sensitivity, and
a detector needs both measured on the same agent, tasks and trial count.

Both are most likely to fail for the same reason: the thresholds have never met
a real stochastic agent. No stub can establish either.

**Hard stop condition.** If the first end-to-end attempt does not produce a
verdict, stop and record why. Do not fix forward more than **once**. If a
second attempt also fails, the milestone is recorded as not achieved and the
defect is fixed offline with a test that reproduces it — the rule the GPU
deployment path was closed under, applied before the money is spent rather than
after.

---

## 1. What AgentSeism is

CI for stochastic AI agents: decide whether a candidate change made an agent
materially worse than a compatible baseline, and if so give evidence and
localization useful for a merge or debug decision. Outcome evidence decides the
verdict; trace analysis explains a confirmed regression and never blocks a
merge on its own. Research validates and promotes the product; it is not the
mainline.

## 2. What existing code we keep

The entire product path, which is already on `master` and already works:
`cli.py` (`init`, `baseline`, `check`), `contract.py`, `resolve.py`,
`pr_report.py`, `runner/`, `execution.py`, `contracts/default.yaml`, and their
130 passing tests. Nine of ten vertical-slice stages are WORKING; the product
imports nothing from the research code.

## 3. What recent work we merge/cherry-pick/archive/drop

Nothing merges. The 80-commit branch contains **no** generic product
functionality: it is a pre-registered GPU experiment that produced zero
experimental cells, plus its protocol machinery and evidentiary record. Keep it
all — archived as research, not deleted.

Cherry-pick candidates, none urgent: the budget state machine, artifact/digest
provenance handling, and the Docker test guard. All three are generically
useful and all three are entangled with pilot vocabulary; port them when the
product needs them, not before.

The `56ea5fe` PYTHONPATH fix stays with the script it patches. Its regression
test's *technique* — run a script's declared imports from outside the
repository — belongs in `INVARIANTS.md`, because the 126-assertion harness
passed with that bug present.

## 4. The single next product milestone

One real agent change, end to end, on a real pull request. The only missing
implementation is a GitHub Action that runs `seism check` and posts the report;
everything else is built and tested. 50 invocations, roughly $5–15, no GPU.
It is accepted on a paired control and not on either half: an unchanged
candidate must return PASS (specificity — noise does not raise an alarm) *and* a
deliberately degraded candidate must return REGRESSION with an interval
(sensitivity — a real regression does). Same agent, same 5 tasks, same 5 trials.
The check goes red on a real PR and a reader can decide from the comment alone. Stop after one fix-forward.
