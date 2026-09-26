# AgentSeism — Intervention Contract

**Status:** Design Draft v0.3 · **contract only, not implemented**
**Scope:** V1 causal attribution
**Related:** [`DESIGN.md`](DESIGN.md) · [`DESIGN-FEATURE-PROJECTION.md`](DESIGN-FEATURE-PROJECTION.md)

## 1. Why this exists now

V0 localizes weak points by association. Association cannot distinguish a source
from its propagated consequences (feature-projection doc §21), and on an
aggregate-only schema the V0 score is correlation re-weighted by feature
variability — which is not a method contribution.

The answer is not a better weighting. It is intervention:

```text
Localization
     ↓
candidate weak points
     ↓
intervene on one feature
     ↓
resume execution
     ↓
did the outcome distribution change?
     ↓
causal attribution
```

This turns the correlation baseline from a threat into part of the argument:

> Correlation can localize suspicious features. It cannot tell where variation
> was **introduced** from where it was merely **inherited**.

The contract is written now, before Week 5, because the hard part is not the
statistics. It is the question of how to intervene on an execution feature of an
arbitrary agent and continue running — and that question should shape the trace
format while the trace format is still cheap to change.

---

## 2. Contract

```python
def intervene(
    run: Run,
    feature: str,
    value: Any,
    *,
    resume_from: str | None = None,
) -> Run:
    """Re-execute `run` with `feature` forced to `value`, and return the new run."""
```

Read as a `do` operator over an execution feature:

```text
P(Y)              observed outcome distribution
P(Y | do(f = v))  outcome distribution when f is forced
```

The causal effect of a feature is the distance between those two distributions,
estimated over repeated interventions:

```text
Effect(f) = D( P(Y | do(f = v_a)), P(Y | do(f = v_b)) )
```

with `v_a`, `v_b` drawn from the modes the feature actually took in observed
runs. Using observed values matters: an effect measured at a value the agent
would never produce says nothing about the agent's own fragility.

---

## 3. The hard part: resuming execution

An execution feature is a *projection*, so it generally has no single point in
the raw trace to overwrite. Three resumption strategies, in increasing order of
fidelity and cost:

### 3.1 Prompt-level injection (approximate)

Rewrite the agent's context so the forced value is what it sees, then run the
remainder normally.

- Works for any agent that takes a prompt.
- Cheap, and honest about being approximate: the agent may reject or reinterpret
  the injected value, so the intervention is *attempted*, not guaranteed.
- Requires reporting an **intervention compliance rate** — how often the forced
  value survived into the projected feature of the new run. An effect measured
  over non-compliant runs is not an effect.

### 3.2 Replay with substitution

Replay the recorded raw trace up to the point the feature is determined,
substitute, and let the agent continue live from there.

- Needs the agent to be resumable from a message history — true for the ReAct
  agents V0 targets, since their state *is* the message list.
- Needs the substitution point to be identifiable in the raw trace. This is the
  reason the raw trace is stored untruncated even though V0 does not rank it.

### 3.3 Checkpoint and resume (highest fidelity)

Snapshot agent state before the feature is produced, force the value, resume.

- Requires framework support (LangGraph checkpointers provide this).
- Not available for arbitrary agents, so it is an adapter capability, not a core
  assumption.

The adapter declares which strategies it supports:

```python
class Intervenable(Protocol):
    def intervention_strategies(self) -> tuple[str, ...]: ...
    def intervene(self, run, feature, value, *, strategy): ...
```

A feature that no strategy can force is **not intervenable**, and must be
reported as such rather than quietly scored by association alone.

---

## 4. What gets reported

For each candidate weak point:

```text
feature            evidence_set
strategy           replay-with-substitution
compliance         0.86
outcome shift      0.41
   P(Y | do(a))    {A: .81, B: .19}
   P(Y | do(b))    {A: .22, B: .78}
localization rank  1
```

Two failure modes must be reported, never hidden:

1. **Low compliance** — the intervention did not take. The number is about the
   harness, not the agent.
2. **High localization rank, no effect** — the feature inherited its variation.
   This is the result that makes the paper, so it must survive contact with the
   reader.

---

## 5. Evaluation

Ground truth stays the injected-source experiment: inject variation at a known
feature, hide the label, and ask whether intervention-based attribution recovers
the source where association-based localization ranks the consequence just as
highly.

The claim to earn:

> Intervention separates introduced variation from inherited variation; the
> localization score and the correlation baseline do not.

If intervention cannot be implemented reliably for real agents, that is itself
the finding, and the thesis should be re-judged rather than patched with more
score terms.

---

## 6. Non-goals

Automatic repair · counterfactual generation for arbitrary agents · a universal
resumable-agent abstraction · intervening on features the adapter cannot force.
