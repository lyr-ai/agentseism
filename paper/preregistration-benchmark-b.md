# Pre-registration — Benchmark B pilot

Written before any Benchmark B run. Nothing below was chosen after seeing data
from the agent it describes. The GAIA Week 1 pilot is complete and reported in
`experiments.md`; its numbers are the comparison point, not a result to defend.

## Why this document exists

The GAIA pilot produced no positive result and two measurement defects that were
only caught because §5 of the runbook required checking instrumentation before
reading numbers. Both defects flattered the data. A pilot whose success criteria
are written after the numbers arrive has no such protection, so the criteria are
written here first.

## Primary outcome definition

**A deterministic, discrete conclusion. No LLM judge.**

Comparing two long free-text reports would make outcome divergence 1.0 on every
pair, which is the failure that made `evidence_set` unidentifiable on GAIA,
relocated to the outcome. An LLM judge would fix that by introducing

    Y_observed = Y_agent + Y_judge

and this project has spent its effort removing measurement contamination
(per-call UUIDs, a harness recursion guard, cross-task pooling), not adding it.

The outcome must therefore be a value the agent commits to that can be compared
exactly, in a task where several such values are defensible.

## Hypotheses

**H1 — consequential variation.** Variation survival exceeds the GAIA L1 value of
0.152. Stated as a direction, not a significance test: 4x5 cannot support one.

**H2 — identifiability.** At least one declared execution feature shows, within a
single task, both enough pairs where it changed and enough pairs where it held
still. This is the more important of the two. GAIA scored 0 of 6.

H2 can hold while H1 fails, and that combination is still progress: it would mean
the regime supports estimation even where variation is mostly absorbed.

## Budget rule, fixed in advance

Calibrate with 1 task x 1 run, then:

| observed cost per run | pilot size |
|---|---|
| <= $1  | 8 tasks x 5 runs |
| $1-$3  | 4 tasks x 5 runs |
| $3-$6  | 2 tasks x 5 runs |
| > $6   | stop; reconsider configuration or benchmark before spending |

Five runs per task is the floor, not the target. Three runs give three pairs,
and "contrast exists" or "contrast does not" would then turn on one coin flip.
Task count is what gets cut, never trials.

## Task selection

Tasks are fixed by an objective rule applied before running: multi-step research
or analysis, an outcome expressible in a finite decision space, taken in the
benchmark's own order, first N satisfying the rule. No task is selected, dropped,
or reordered after seeing its outcome variation.

**Unresolved at time of writing, and blocking.** A survey of public deep-research
benchmarks found the field actively engineering ambiguity *out*, because
ambiguity makes grading hard: DRACO "turns ambiguous queries into well-defined
tasks", LiveResearchBench is "designed to be more unambiguous", DRB-II grades
reports against 9,400 binary expert criteria. Those are report-quality
benchmarks, and none yields a discrete decision over which several answers are
defensible. Selecting our own questions instead would put the ambiguity in by
hand, which is the objection that ruled out a synthetic benchmark for now.

The pilot does not start until a task source satisfying the rule is frozen here.

## Analysis rules

- Inference is within-task. Run pairs are not exchangeable across tasks; a global
  permutation measures task identity, as demonstrated on the GAIA data.
- Amplification is the risk difference `P(dY|df) - P(dY|!df)`, reported with both
  arms and their sample sizes, `None` when either arm is empty.
- **No schema change after seeing pilot outcomes**, unless a measurement-validity
  defect can be demonstrated independently of the outcome -- as `gaia-mz/1` was,
  where evidence similarity of 1 was impossible by construction and the argument
  never referenced a result.

## Stopping condition

If the pilot shows outcome variation but still zero identifiable features, **do
not move to a third benchmark.** Two benchmarks failing the same way is evidence
about the method, not about benchmark choice: it would suggest that agent
execution does not decompose into discrete features that recur, and the question
becomes whether the object of study should be a continuous or trajectory-level
representation instead. Switching benchmarks until something works would make any
eventual positive result uninterpretable.
