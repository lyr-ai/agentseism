# Product shape — a local, GitHub-native regression CLI

**Status:** shape recorded, 2026-09-20. **Mode 3 was truncated in transit and
is not invented here.** Nothing implemented beyond the contract layer.

## 1. What it is

> A **local, GitHub-native agent regression testing CLI / pytest plugin.**

Not another LangSmith, and not a SaaS dashboard first. What a developer
downloads is a tool that answers, in an existing agent repository and with very
little configuration:

> I changed a prompt, a tool, a context policy or the agent loop. Did this PR
> actually make the agent worse — and if so, where did it most likely break?

## 2. First use, four steps

```bash
pip install agentseism
agentseism init            # .agentseism/{contract.yaml,tasks.yaml,baselines/}
```

The user says how to run a task and how to judge success:

```yaml
runner:
  command: "python run_agent.py --task {task_file}"
outcome:
  evaluator: "python check_result.py {artifact_dir}"
features:
  task_success:     {gate: true,    regression_threshold: 0.10}
  recovery_success: {gate: true,    regression_threshold: 0.15}
  cost_per_success: {gate: warning, regression_threshold: 0.25}
```

```bash
agentseism baseline --tasks tasks.yaml --trials 5
agentseism check --baseline main
```

The baseline stores outcomes, normalized traces, cost and latency, the serving
fingerprint, the contract hash, and is immutable.

The PR comment is the product:

| Capability | Baseline | PR | Change | Decision |
|---|---:|---:|---:|---|
| Task success | 82% | 80% | −2 pp | PASS |
| Error recovery | 74% | 43% | −31 pp | **REGRESSION** |
| Cost/success | $0.41 | $0.55 | +34% | WARNING |

```text
REGRESSION
Primary signal: malformed-call recovery decreased by 31 pp.
RCA: first consistent separation after invalid tool-call handling;
     candidate retries without the recovery instruction in 8/10 affected runs.
Unaffected: runs without malformed calls show no detected outcome regression.
```

## 3. Modes

**`check`** — the daily product. Is this comparable; which capability
regressed; is the evidence sufficient; should the merge be blocked; where does
it start. This is the entry point most likely to get real users.

**`mutate`** — tests the test suite, not the agent. *Can your task set detect
"someone deleted the error-recovery hint"?*

```text
Mutation: remove_recovery_hint
Expected signal: recovery_success decreases
Observed: −28 pp
Outcome: KILLED
Negative control: clean-run success −1 pp
```

This is the honest home for mutation testing in the product: **suite quality,
not agent quality.** It also keeps mutations where the contribution matrix put
them — apparatus, not a claim.

**Mode 3** — truncated in transit, not reconstructed.

## 4. The conflict this creates with the frozen contract

The user-facing contract above is three lines per feature. The contract layer
committed at `5d2d650` **requires eight** on every gating feature: evaluator,
independent unit, effect, regression direction, practical threshold,
uncertainty, minimum evidence, invalid policy.

Both requirements are right and they are not compatible as written:

- a developer must not have to understand risk difference, bootstrap or
  independent unit to run `agentseism check`;
- a metric must not be decided after the analysis is seen, which is exactly
  what the eight fields prevent.

### Resolution: resolved defaults, hashed and reported

The user writes a **surface contract**. The tool resolves it against built-in
defaults into an **effective contract**, and it is the effective one that is
validated, hashed and printed.

```
surface contract (3 lines)  →  resolve defaults  →  effective contract (8 fields)
                                                          ↓
                                            validated · hashed · in the report
```

This keeps both properties, and the reason it does is the ordering: the
defaults are fixed **in the tool**, before anyone sees a number. A default
chosen by the tool in advance is not a metric chosen by the author afterwards.

Three rules make that true rather than merely stated:

1. **Every report prints the effective contract**, not the surface one. A
   reader can see that `task_success` used `risk_difference` with a paired
   bootstrap and a 5-scenario minimum, even though the author wrote one line.
2. **The hash covers the effective contract.** Changing a default in a new
   version of the tool changes the hash, so two runs are not silently compared
   across different resolutions.
3. **A resolved default is marked as resolved.** `source: default` versus
   `source: author` per field, so a reviewer can tell what was chosen from what
   was inherited.

### What this changes in the code

`contract.py` gains a `resolve()` step ahead of `validate()`, and `validate()`
keeps its current strictness — it now validates the *effective* contract, which
is always complete. Nothing in the frozen semantics moves: the eight fields are
still mandatory, they are simply no longer all typed by hand.

**Not implemented yet.** The contract layer stops where the review asked it to
stop, and this is recorded as the next change rather than made silently.

## 5. Open

- Mode 3.
- Whether `agentseism init` should write the surface or the effective contract
  (surface is friendlier; effective is self-documenting).
- Whether `mutate` ships in the first version at all, given that `check` is the
  thing that earns a download.
