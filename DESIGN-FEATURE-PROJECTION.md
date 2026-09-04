# AgentSeism — Execution Feature Projection & Alignment

**Status:** Design Draft v0.2
**Scope:** V0 alignment and attribution model
**Related:** [`DESIGN.md`](DESIGN.md)

## 1. Problem

Two executions of the same LLM agent may produce different raw execution graphs.

A ReAct-style agent may execute:

```text
Run A

consider_question → search → consider_question → calculator → submit_final_answer
```

while another run executes:

```text
Run B

consider_question → search → consider_question → search
→ consider_question → calculator → consider_question → submit_final_answer
```

Naively aligning:

```text
model_call[0] ↔ model_call[0]
model_call[1] ↔ model_call[1]
model_call[2] ↔ model_call[2]
```

is invalid. The third model call in one run may serve a completely different
purpose than the third model call in another run.

> **Raw event occurrence is not a reliable cross-run identity.**

Solving arbitrary graph alignment is a separate large research problem. V0 does
not attempt node-level graph isomorphism.

---

# 2. Core Design Principle

```text
Raw Execution Trace
        ↓
Agent Adapter
        ↓
Comparable Execution Features
        ↓
Cross-run Variation Analysis
        ↓
Outcome Attribution
```

The adapter converts arbitrary or variable-length raw execution into a stable
set of **execution features**. AgentSeism compares those features across
repeated runs.

---

# 3. Execution Feature

> **A comparable representation extracted from one execution that captures an
> aspect of agent behavior which may vary across runs.**

```python
@dataclass
class ExecutionFeature:
    name: str
    value: Any
    metadata: dict = field(default_factory=dict)
```

For a ReAct agent: `tool_set`, `tool_sequence`, `tool_call_count`,
`evidence_set`, `initial_plan`, `pre_final_reasoning`.

For a fixed RCA pipeline: `evidence_selection`, `hypothesis`, `decision`,
`verification_result`.

AgentSeism core does not assign semantic meaning to feature names. The adapter
defines them.

---

# 4. Why Feature Projection Instead of Stage Alignment

A "semantic stage" abstraction assumes stable high-level phases. That works for
`retrieve → analyze → decide` and works poorly for `think → tool → think → tool`.

Feature projection handles both. A dynamic trajectory
`search, search, calculator, search` projects into:

```text
tool_set          = {search, calculator}
tool_sequence     = [search, search, calculator, search]
tool_call_count   = 4
```

Variable-length execution becomes comparable without graph matching.

---

# 5. Raw Trace Representation

The raw trace remains available and is preserved for debugging, later causal
intervention, future automatic feature extraction, and visualization.

```python
@dataclass
class RawEvent:
    id: str
    run_id: str
    event_type: str
    input: Any
    output: Any
    parent_ids: list[str]
    metadata: dict
```

V0 attribution does not operate on raw event identity.

---

# 6. Feature Projection Contract

```python
def project(trace: RawTrace) -> dict[str, ExecutionFeature]:
    ...
```

Output feature names must be stable across repeated runs.

---

# 7. Features Must Be Defined Before Outcomes Are Examined

Feature design introduces researcher degrees of freedom.

> **Adapter features must be defined from agent architecture and trace semantics
> before analyzing experimental outcome relationships.**

1. inspect agent architecture
2. define candidate features
3. freeze adapter version
4. run experiment
5. analyze weak-point results

Every experiment records `adapter_version` and `feature_schema_version`.

---

# 8. GAIA / ReAct V0 Feature Schema

Intentionally small.

| feature | question it answers |
|---|---|
| `tool_set` | did the agent choose different capabilities? |
| `tool_sequence` | did the execution path differ? |
| `tool_call_count` | did the agent take a longer or shorter path? |
| `evidence_set` | did different evidence acquisition lead to different outcomes? |
| `initial_plan` | did runs diverge before tool execution? |
| `pre_final_reasoning` | did high-level reasoning differ before submission? |

`tool_set` and `tool_sequence` are distinct: two runs may share a tool set while
their paths differ, which means capability choice is stable while path behavior
varies. `pre_final_reasoning` may vary greatly textually, so it also serves as a
negative-control-like feature.

---

# 9. Outcome Is Not an Attribution Feature

If `feature = final_answer` and `outcome = final_answer`, then
`Association(feature, outcome) = 1` by construction, and ranking it would be
tautological.

```python
class ObservationRole(Enum):
    FEATURE = "feature"
    OUTCOME = "outcome"
```

Attribution candidates include only `FEATURE` observations.

---

# 10. Explicit Outcome Exclusion

Never silent:

```text
Excluded from attribution:
- final_answer (declared outcome)
```

---

# 11. Cross-Run Alignment

Once runs are projected into stable feature names, alignment is feature-name
based. No raw node correspondence is required.

```text
                 Run 1        Run 2        Run 3
tool_set           A            A            B
tool_sequence      S1           S2           S3
tool_call_count     3            5            4
evidence_set       E1           E2           E3
outcome            Y1           Y2           Y3
```

---

# 12. Missing Features

Not every feature exists in every run. Missingness is an observable execution
difference: `D(MISSING, x)` is maximal, or handled by the feature comparator.

---

# 13. Feature Comparators

```text
tool_set          → Jaccard similarity
tool_sequence     → sequence similarity
tool_call_count   → normalized numeric distance
evidence_set      → set similarity
initial_plan      → semantic similarity
```

Adapters may declare `FeatureSpec(name=..., comparator=...)`; the core supplies
generic defaults.

---

# 14. Local Variation

$$V_f = E_{i,j}[D(F_{i,f}, F_{j,f})]$$

High variation alone does not imply weakness.

---

# 15. Outcome Association

$$A_f = Association(D(F_{i,f},F_{j,f}), D(Y_i,Y_j))$$

This prevents purely cosmetic variation from dominating the ranking.

---

# 16. Propagation

In a fixed pipeline, downstream order is explicit. In a dynamic ReAct execution,
feature projection may not define a chain.

- **Ordered features** — adapter declares order; propagation uses downstream
  feature divergence.
- **Unordered/global features** — propagation is unavailable, reported as
  `None`. The score must not invent an ordering.

---

# 17. Weak-Point Score

```text
unordered   W_f = V_f × A_f
ordered     W_f = V_f × A_f × P_f
```

The report must indicate which scoring mode was used.

---

# 18. Weak Point Definition

> **An execution feature whose variation is strongly associated with downstream
> outcome variation across repeated runs.**

Not necessarily the first difference, the largest local difference, the causal
root, or a failure. It is a candidate fragility point worth engineering
investigation.

---

# 19. Structural Variation Is a Feature, Not an Alignment Failure

```text
Run A: search → calculator
Run B: search → search → calculator → search

tool_set          same
tool_sequence     different
tool_call_count   different
```

The graph difference is represented explicitly as behavior.

---

# 20. Avoid Double-Counting Related Features

`tool_sequence`, `tool_call_count` and `tool_set` may all reflect one underlying
change. Reporting must not claim "three independent weak points"; related
features are labelled as one **execution-feature family**, with their
correlation reported.

---

# 21. Known Limitation: Downstream Inheritance

If the true source is `evidence_set` and it changes reasoning, then tool
sequence, then the outcome, several projected features correlate strongly with
the outcome. Association-based attribution cannot reliably separate source from
propagated consequence. V0 scores remain **associational**, and the paper must
say so.

---

# 22. Correlation Baseline Risk

The synthetic harness indicates a simple correlation baseline may be strong.
If `AgentSeism ≈ correlation-only` on real agents and controlled interventions,
the proposed score is not a sufficient research contribution, and the next
method should introduce controlled intervention or counterfactual replay.

**This is a planned falsification test, not an implementation detail.** The
pilot reports it directly.

---

# 23. Negative Control Requirement

V0 deliberately includes features with high local variation and little expected
outcome impact, such as `pre_final_reasoning` wording:

```text
high local variation + low outcome association = low weak-point score
```

This validates that AgentSeism is not merely ranking whatever changes most.

---

# 24. Feature Schema Freeze

```text
inspect architecture → define schema → freeze → commit adapter version
→ run pilot → analyze
```

If the schema changes after pilot analysis, record it as a new version and rerun
the full experiment. Do not mix results across schemas.

---

# 25. Pilot Before Scale

Before `50 tasks × 10 trials`, run `10 tasks × 5 trials` and check:

1. **Outcome variation** — is there measurable variation at all?
2. **Feature variation** — do projected features vary?
3. **Feature usefulness** — do some features relate to outcome variation?
4. **Comparator sanity** — are similarities behaving reasonably?
5. **Baseline strength** — does correlation-only already explain everything?

Only scale if the pilot passes.

---

# 26. GAIA Pilot Success Criteria

1. raw loop length varies across runs;
2. projected features remain comparable;
3. outcome variation exists for at least some tasks;
4. not all high-variation features have high outcome association;
5. one or more execution features show meaningful relation to behavioral mode
   changes.

It does **not** need to establish causal attribution.

---

# 27. Updated V0 Architecture

```text
                    Agent Run
                       │
                       ▼
               Raw Trace Collector
                       │
                       ▼
                 Agent Adapter
                       │
                       ▼
              Feature Projection
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
   Execution Features             Outcome
          │                         │
          └────────────┬────────────┘
                       ▼
               Variation Analysis
                       │
                       ▼
              Outcome Association
                       │
                       ▼
              Weak-Point Ranking
```

The outcome is deliberately outside the attribution feature set.

---

# 28. Core API

```python
scan(
    agent=agent,
    cases=cases,
    trials=10,
    projector=ReActProjector(),
    outcome=final_answer,
)
```

The adapter may also provide feature-specific comparators.

---

# 29. What V0 Explicitly Does Not Solve

Arbitrary raw graph alignment · graph isomorphism · automatic semantic-stage
discovery · automatic feature discovery · causal root-cause attribution ·
universal agent ontology · automatic repair.

---

# 30. Paper Framing

> **AgentSeism projects heterogeneous agent executions into comparable execution
> features and measures which feature variations are most strongly associated
> with downstream behavioral variation.**

Do not claim AgentSeism aligns arbitrary agent graphs. Do not call associational
ranking causal attribution. V0 is **weak-point localization**; reserve **causal
attribution** for intervention-based versions.

---

# 31. Research Progression

```text
V0   raw trace → hand-defined execution features → weak-point localization
V1   controlled intervention → causal weak-point attribution
V2   automatic feature discovery → semantic execution abstraction
V3   arbitrary dynamic traces → automatic end-to-end diagnosis
```

---

# 32. Implementation Notes

The `name + occurrence` mechanism is kept but redefined: it aligns
`ExecutionFeature.name`, not arbitrary raw events. Occurrence remains useful only
when the adapter intentionally exposes repeated semantic features.

Outcome exclusion lives in core, not in the GAIA adapter: attribution rejects
`OUTCOME` observations by construction.

---

## The conceptual change

Old model:

> Different graphs → align semantic stages → find weak point.

New model:

> Different graphs → project both executions into comparable behavioral features
> → determine which feature variations are associated with outcome variation.

This preserves the phenomenon the GAIA implementation exposed: sometimes **the
path itself** — tool set, tool order, loop length, acquired evidence — is exactly
what varies, and therefore exactly what AgentSeism should measure.
