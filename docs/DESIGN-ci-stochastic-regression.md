# AgentSeism: Budget-Aware Stochastic Regression Debugging for Agent CI

**Status:** Design proposal  
**Date:** 2026-09-19  
**Primary product surface:** GitHub pull-request check  
**Scope:** LLM agents with inspectable execution traces  
**Evidence in §2 verified against `paper/experiments.md` on 2026-09-19.**  

## 1. Executive summary

AgentSeism should not compete as another general-purpose agent evaluation framework. Existing products already run agent test suites in CI, compute evaluator scores, compare versions, and block merges.

The narrower opportunity is **stochastic regression debugging**:

> Given a limited evaluation budget, determine whether a candidate agent change introduced a consequential reliability regression, identify newly emerging failure modes, and localize the earliest meaningful execution divergence that explains where investigation should begin.

The initial product is a CI plugin that compares a cached baseline with a pull-request candidate. It adaptively allocates repeated runs, gates on outcome-level evidence, and uses trajectory analysis to diagnose—not automatically prove—the source of a regression.

The first product claim to validate is:

> AgentSeism can detect and localize a consequential behavioral regression that ordinary pass-rate or final-answer evaluation misses, using a practical number of agent runs.

## 2. Motivation

Agent executions are stochastic even at temperature zero. Model-serving nondeterminism, tool outputs, environment ordering, timestamps, and accumulated decisions can lead the same initial state to different trajectories and final repository states.

Current AgentSeism evidence already demonstrates that this is not merely theoretical:

- One SWE-bench task produced **12 distinct final repository states across 13 independent runs** at temperature zero. Twelve of the thirteen first pass through one byte-identical intermediate state, and those twelve end in eleven distinct states. The thirteen runs span two context lengths and two transport paths, and none of the three batches was registered as a test of the topology — this is a descriptive stability observation, not a confirmed result. (`paper/experiments.md`, 2026-09-08.)
- A 20-run experiment found no useful early signal at horizon 14: 19 of 20 runs still shared one 438-byte state, and the candidate feature measures `d = 0.23` in the very data that suggested it.
- Separation reaches a **medium** effect around horizon 24 and a **large** one around horizon 28 — roughly 73–85% of a median 32–33-step execution. The sample is **16 passing and 4 failing runs**; four failures is thin, and the effect sizes carry that uncertainty.
- The OpenRCA **discovery** batch is *consistent with* decision divergence preceding evidence divergence: runs commit early, commit late, or focus on different services, with correct and incorrect outcomes. The supporting test is `commit_step → reason`, `A_f = +0.34`, `p = 0.063` — underpowered, and it does not survive Bonferroni correction at `alpha = 0.0042`. The repository records the features as **not established as amplification points**; Bank is frozen as the discovery set and confirmation requires a held-out system. This observation motivates the product; it does not yet evidence it.

These observations imply two product requirements:

1. A single run is insufficient evidence of reliability.
2. Different trajectories are not inherently regressions; only consequential changes should affect the merge decision.

## 3. Product definition

### 3.1 User

The initial user is an engineer or small team maintaining an agent whose behavior may change after modifying prompts, tools, memory, orchestration logic, models, or dependencies.

### 3.2 Job to be done

Before merging a pull request, the user needs to know:

1. Did the candidate become materially less reliable than the baseline?
2. Did it introduce a new failure mode even if the average score looks unchanged?
3. Where did failing candidate executions first diverge meaningfully from successful baseline behavior?
4. Is the evidence strong enough to block the merge, or is more sampling required?

### 3.3 Positioning

**AgentSeism is a stochastic regression debugger for agent CI.**

It is not initially:

- a generic observability platform;
- a replacement for DeepEval, Promptfoo, LangSmith, or cloud evaluation services;
- a guarantee of deterministic agent trajectories;
- a causal attribution engine without controlled intervention;
- a large benchmark-hosting service.

AgentSeism should ingest traces from existing frameworks where practical. Those systems can provide execution and ordinary evaluator scores; AgentSeism provides repeated-run comparison, novel-mode detection, divergence localization, and budget-aware evidence collection.

## 4. Design principles

### 4.1 Gate on outcomes; diagnose with trajectories

Trajectory identity is not a quality target. Two agents may take different valid paths and both succeed. The CI decision therefore uses outcome-level evidence such as correctness, policy violations, cost, latency, or task-specific invariants.

Trajectory features are used to explain outcome changes and identify new risky behaviors.

```text
trajectory variation
        ↓
behavioral modes and state variation
        ↓
consequential outcome regression  ← merge gate
```

An exception is an explicitly prohibited behavior—such as an unauthorized tool action—which is itself a task outcome and may gate immediately.

### 4.2 Observed change is not causal attribution

AgentSeism may report that a candidate diverged at a tool choice, memory retrieval, planning decision, or environment observation. This is **localization**, not proof that the component caused the outcome.

Causal language is allowed only after a controlled intervention or ablation reproduces the expected outcome change.

### 4.3 Spend budget on tasks before repetitions

Repeated trials on one task estimate that task's stochasticity; they do not provide independent evidence about performance across tasks. With a fixed budget, AgentSeism should first cover more representative tasks and then add trials selectively where instability or baseline/candidate disagreement appears.

### 4.4 Preserve experimental independence

Forks sharing a prefix are useful for intervention analysis but are not independent histories. CI reliability estimates must count independently initiated runs separately from shared-prefix forks and report effective independent sample size.

### 4.5 Report uncertainty explicitly

Small samples should not be disguised as certainty. The report must distinguish observed behavior, suspected regression, confirmed regression, and insufficient evidence.

## 5. CI workflow

### 5.1 Configuration

An initial configuration may look like:

```yaml
suite: agent-regression
baseline: main
candidate: pull-request

budget:
  initial_trials_per_task: 2
  max_trials_per_task: 8
  max_total_cost_usd: 20

gates:
  max_success_rate_drop: 0.10
  max_cost_increase: 0.25
  prohibited_behaviors:
    - unauthorized_tool_call

diagnostics:
  detect_new_failure_modes: true
  localize_first_meaningful_divergence: true
```

Exact schema and thresholds remain provisional until the validation experiment establishes useful defaults.

### 5.2 Execution flow

1. Load the versioned test suite and cached baseline runs.
2. Select tasks affected by the pull request, plus a small sentinel set.
3. Run the candidate initially two or three times per selected task.
4. Normalize raw traces through framework adapters into a common event model.
5. Compute outcome metrics and trajectory features.
6. Identify baseline/candidate disagreements, unstable tasks, and potentially novel failure modes.
7. Allocate additional candidate runs only to ambiguous or high-risk tasks, stopping at a cost or trial cap.
8. Evaluate merge gates using outcome evidence and uncertainty.
9. For suspected or confirmed regressions, align relevant trajectories and localize the first consequential divergence.
10. Publish a PR check with the decision, confidence, cost, evidence, and diagnostic links.

## 6. System architecture

### 6.1 Components

**CI orchestrator**

- Resolves baseline and candidate versions.
- Enforces cost, time, and concurrency budgets.
- Schedules initial and adaptive trials.
- Produces the final check conclusion.

**Trace adapters**

- Convert framework-specific traces into a common representation.
- Preserve raw events for auditability.
- Record model configuration, tool observations, environment identity, and execution metadata.

**Outcome evaluator**

- Supports deterministic task checks first.
- Accepts user-defined evaluators and optional LLM judges.
- Treats judge retries as additional samples and records them explicitly.

**Behavioral mode analyzer**

- Extracts tool, decision, state, cost, latency, and final-artifact features.
- Groups executions into interpretable behavioral or failure modes.
- Detects candidate modes not represented in the baseline evidence.

**Divergence localizer**

- Aligns partial-order execution events rather than relying only on raw step index.
- Separates aggregate weak-point ranking from positioned divergence reports.
- Finds the earliest difference that is associated with a later consequential outcome.
- Uses “associated with” or “localized at,” not causal language.

**Evidence store**

- Caches immutable baseline traces and derived features.
- Versions task, environment, evaluator, adapter, and model configuration.
- Prevents accidental comparison of incompatible experimental conditions.

**PR reporter**

- Shows the merge recommendation and why.
- Separates outcome evidence from diagnostic evidence.
- Makes uncertainty and additional-run cost visible.

### 6.2 Common trace record

The minimal normalized event should include:

```text
run_id, independent_history_id, task_id, version
event_id, parent_event_ids, logical_position
event_type, component, input_digest, output_digest
tool_name, state_before_digest, state_after_digest
timestamp, latency, token_usage, monetary_cost
environment_digest, model_config_digest
outcome_labels, raw_event_reference
```

`independent_history_id` prevents multiple shared-prefix forks from being counted as independent reliability samples.

## 7. Statistical design under a limited budget

The goal is not to estimate every success probability precisely. A small personal budget cannot reliably distinguish, for example, an 82% success rate from 86% across a broad population of tasks. The first goal is to detect large, practically important regressions and new consequential behaviors.

### 7.1 Paired task comparison

Baseline and candidate should run against the same task definitions and pinned environment snapshots. Analysis should use paired task differences wherever possible to reduce variance from task difficulty.

### 7.2 Cached baseline

A validated baseline is reused across pull requests until the agent, task, evaluator, model, or environment compatibility key changes. The report must show when baseline evidence was collected and whether it is still compatible.

### 7.3 Adaptive trials

Initial trials are run broadly. More trials are allocated when:

- baseline and candidate outcomes disagree;
- either arm shows instability;
- a candidate trace falls outside known behavioral modes;
- a high-severity prohibited behavior occurs;
- the decision interval remains near a merge threshold.

The sequential procedure must account for repeated looks at the data. The MVP may begin with conservative confidence sequences or a pre-registered stopping rule rather than an uncorrected repeated significance test.

### 7.4 Practical effect thresholds

AgentSeism should not spend money proving negligible changes. Each gate needs a minimum practically important effect, such as:

- success-rate drop of at least 10 percentage points;
- cost increase of at least 25%;
- latency increase beyond a service-specific bound;
- any occurrence of a severity-one prohibited behavior;
- a recurrent new failure mode with a defined severity.

Defaults are hypotheses, not finalized product settings.

### 7.5 Evidence states

| State | Meaning | CI action |
|---|---|---|
| No material change detected | No gate crossed within current evidence | Pass |
| Observed behavioral change | New path or mode observed without demonstrated harm | Pass with annotation |
| Suspected regression | Harmful signal exists but evidence is below confirmation threshold | Neutral/warn; optionally request more runs |
| Confirmed regression | Predefined outcome gate crossed with adequate evidence | Fail |
| Insufficient evidence | Budget exhausted before a defensible decision | Neutral, never silently pass as proven safe |

## 8. PR report

The first report should answer the decision question before showing analysis details.

```text
AgentSeism: SUSPECTED REGRESSION

Outcome
- Final task success: no material aggregate change detected
- Candidate cost: +31% on 2 affected tasks
- New failure behavior: wrong-tool selection followed by recovery

Evidence
- 8 candidate trials across 3 tasks
- 3 independent occurrences of the new mode
- Baseline: 0 occurrences in 18 compatible cached trials
- Additional runs stopped at the configured $20 budget

Localization
- First meaningful divergence: tool selection after repository search
- Baseline mode: inspect configuration → edit target file
- Candidate mode: call unrelated tool → fail → retry → recover
- Interpretation: localization only; causal attribution not established

Recommendation
- Warn. Investigate tool-routing change before merge.
```

This demonstrates the intended advantage: final success may remain unchanged while cost and latent failure risk regress.

## 9. Validation experiment

### 9.1 Objective

Demonstrate one controlled case where ordinary final-output evaluation considers the candidate acceptable, while AgentSeism detects a consequential behavioral regression and localizes where it emerges.

### 9.2 Experimental setup

- Select 5–10 tasks from an agent with available traces.
- Freeze task definitions, model/version, environment, tools, evaluator, and analysis protocol.
- Create or select a baseline/candidate pair with similar aggregate final success but a plausible behavioral regression.
- Use independent runs for reliability estimation.
- Start with approximately three trials per task; add trials adaptively under a fixed dollar cap.
- Preserve full raw traces and final artifacts.

Candidate regressions may include:

- a wrong tool call followed by recovery;
- unnecessary retries that increase cost or latency;
- a new failure cluster hidden by unchanged average success;
- unsafe intermediate behavior despite a correct final answer;
- delayed evidence gathering caused by early commitment.

### 9.3 Baselines

Compare against at least:

1. Final success/pass rate only.
2. Aggregate evaluator or LLM-judge score.
3. Cost and latency thresholds without trajectory diagnosis.
4. A general CI evaluation framework, if integration cost is low.

### 9.4 Evaluation metrics

**Detection**

- Did the method flag the planted or independently verified regression?
- False-warning rate on benign trajectory variation.
- Runs and dollars required before reaching a decision.

**Localization**

- Distance between reported divergence and the known intervention/change point.
- Detection lead time before final failure.
- Reviewer judgment of whether the report identifies a useful investigation point.

**Statistical integrity**

- Number of tasks.
- Total trials.
- Effective independent histories.
- Effect sizes and uncertainty intervals.
- Number of adaptive looks and stopping rule used.

### 9.5 Acceptance gate

Proceed to CI-plugin implementation only if the experiment shows all of the following:

1. The regression is consequential and reproducible.
2. A conventional final-output metric misses it or explains it materially less well.
3. AgentSeism detects it within a plausible CI budget.
4. The localized divergence is useful to a developer.
5. The result survives an independent rerun under the frozen protocol.

If these conditions fail, refine the detection problem before building product infrastructure.

## 10. MVP scope

### Included

- One initial agent/framework adapter.
- Local CLI plus GitHub Action wrapper.
- Baseline cache with compatibility keys.
- User-supplied deterministic outcome checks.
- Initial and adaptive repeated runs.
- Outcome, cost, and latency comparison.
- Simple novel-failure-mode detection.
- First meaningful divergence report.
- Explicit evidence level and budget accounting.

### Deferred

- General production observability.
- Real-time monitoring of deployed agents.
- Large hosted benchmark catalog.
- Broad multi-framework adapter coverage.
- Fully automated causal attribution.
- Enterprise dashboard, RBAC, SSO, and private deployment.
- Complex billing and hosted execution.

Observability and benchmark modules remain possible later extensions, but they should not delay validation of the core regression-debugging claim.

## 11. Risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Too few runs | False confidence or noisy warnings | Evidence states, adaptive sampling, effect-size thresholds |
| Too many runs | CI becomes slow and expensive | Cached baselines, task selection, early stopping, hard budgets |
| Benign path diversity | Excessive false alarms | Gate on outcomes; use trajectories diagnostically |
| Shared-prefix dependence | Inflated sample size | Track independent history IDs and report effective N |
| Environment drift | Model blamed for external changes | Pin environment; record tool outputs and compatibility keys |
| LLM-judge variation | Noisy outcome labels | Prefer deterministic checks; store judge samples and retries |
| Spurious localization | Misleading root-cause claims | Use localization terminology; require interventions for causality |
| Existing platforms add similar features | Weak standalone differentiation | Remain framework-neutral and integrate as a diagnostic layer |
| Personal experimental cost | Work stalls before validation | Use public traces, self-hosted models where appropriate, and staged spend gates |

## 12. Product path after validation

The open-source layer can provide local analysis and the GitHub Action. A later paid service may provide persistent history, team reports, cross-PR trends, scalable execution, failure-mode clustering across suites, and enterprise controls.

The earliest commercial signal is not total revenue. It is whether an external team repeatedly relies on the report when deciding whether to merge. A useful sequence is:

1. One convincing reference experiment.
2. A reproducible public demo.
3. Three to five external teams using the CI check.
4. At least one team asking for persistence, collaboration, scale, or private deployment.
5. One or two teams willing to pay.

The same core work remains valuable if the standalone product path is slow: it can become an integration layer, a benchmark, a research contribution, or evidence for agent-infrastructure and reliability roles.

## 13. Immediate next steps

### Phase A — freeze the proof

- Choose the baseline/candidate regression scenario.
- Freeze the task set, environment, evaluator, and budget.
- Define the consequential outcome and minimum practical effect.
- Pre-register the adaptive stopping rule and evidence labels.

### Phase B — run the cheapest decisive experiment

- Reuse compatible baseline traces where possible.
- Run independent candidate histories.
- Record effect size, uncertainty, effective independent N, and cost.
- Compare final-output evaluation with AgentSeism diagnosis.

### Phase C — package the result

- Generate a one-page PR-style report.
- Produce one figure showing same aggregate outcome but different behavioral modes.
- Write the result as an engineering observation without unsupported causal claims.
- Decide whether evidence supports a demo, short paper/workshop submission, or another iteration.

### Phase D — only after the gate passes

- Implement the GitHub Action and minimal configuration schema.
- Add one external framework integration.
- Recruit a small number of design users.

## 14. Decision log

| Date | Decision |
|---|---|
| 2026-09-19 | Define AgentSeism primarily as an Agent CI stochastic regression debugger, not generic observability. |
| 2026-09-19 | Gate on consequential outcomes; use trajectory differences for diagnosis. |
| 2026-09-19 | Treat limited evaluation budget as a core statistical-design constraint and product feature. |
| 2026-09-19 | Use adaptive trials, cached baselines, paired tasks, and effective independent histories. |
| 2026-09-19 | Validate one differentiated regression case before investing in broader CI infrastructure. |
| 2026-09-19 | Preserve “localization, not causality” unless an intervention establishes causal evidence. |

## 15. Open questions

1. Which existing agent and task pair produces the cleanest baseline/candidate proof?
2. What normalized trace subset is sufficient for the first external integration?
3. Which confidence-sequence or sequential decision rule is simplest to explain and implement correctly?
4. Should an insufficient-evidence result be neutral by default or configurable as a CI failure?
5. How should a new failure mode be scored when it is rare but high severity?
6. What baseline invalidation key best balances reuse against experimental comparability?
7. Can the initial product demonstrate a clear diagnostic advantage within a total experiment budget below $20–50?

---

### One-sentence product statement

**AgentSeism helps teams catch and diagnose stochastic agent regressions in CI—before a pull request turns a rare behavioral deviation into a production failure.**
