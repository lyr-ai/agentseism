# AgentAssay audit — and what AgentSeism does next

**Status:** plan. Zero compute. No machine rented, no model called.
**Trigger:** the novelty gate fired (`RELATED-WORK-MATRIX.md` §0).

---

## 0. The rule that makes this an audit rather than a search for an excuse

> **This audit must be able to conclude that AgentAssay is sound and that we
> should stop.**

If the only outcome it can produce is "we found a gap", it is not an audit, it
is motivated reasoning with citations. So the stopping conclusion is written
down first, before any of its evidence is read:

**If AgentAssay handles the eight questions in §2 rigorously, the method-paper
route is abandoned.** AgentSeism then continues as a product implementation, or
around comparability and recoverability — not as a paper making the same claim
with different numbers.

The same discipline as everywhere else in this project: name the outcome that
would stop you, before you look.

---

## 1. What is already decided

- **The main-line claim is dropped.** Budget-aware stochastic agent regression
  testing with a mutation suite is not ours to claim.
- **No mutation-suite pre-registration.**
- **No machine.** C2-H stays sealed, `CONDITIONAL GO`, apparatus intact.
- Prior art blocks the claim **regardless of its quality**. Quality decides
  what we do next, not whether we may claim it.

## 2. The eight questions

Each is a fact about the paper, answerable by reading it. None requires
compute.

| # | Question | Why it matters |
|---|---|---|
| 1 | Are the code and data public? | Determines whether an independent reproduction is even possible |
| 2 | Are the three scenarios real agent workflows, or simulations? | A distribution-level simulation is a different claim from a running agent |
| 3 | Are mutations actually executed, or is their effect sampled from an assumed distribution? | If sampled, the cost result is about the simulator |
| 4 | Is SPRT applied to **paired** baseline/candidate observations? | Unpaired SPRT on a noisy agent is a much weaker test |
| 5 | How are repeated measurements and multiple comparisons handled? | 7,605 trials across 5 models × 3 scenarios × many mutations invites inflation |
| 6 | What is the **denominator** of the 78–100% cost reduction? | Against one fixed-N baseline, or the worst one? A saving is only meaningful against what a practitioner would actually run |
| 7 | Does the behavioural fingerprint treat harmless trace variation as regression? | Our own data says five accepted solutions differed on every trajectory |
| 8 | Is there an `incomparable` state when the model or runtime changes? | It treats model change as a mutation; Gate 9 suggests that can invalidate the comparison rather than constitute one |

Questions 7 and 8 are the two where our existing frozen data already says
something, which is why they are the most likely to be load-bearing.

## 3. What survives either way

Four directions, ordered by how little they overlap.

**A — Comparability before regression.** *When are two agent runs not
comparable at all?* AgentAssay treats a model change as a mutation to be
detected. Gate 9's `0/23` structured-action match says a serving-stack change
can make the comparison invalid rather than informative. This is a different
question, not a better answer to the same one, and we already hold the
evidence.

**B — Does a more powerful trace test false-alarm more?** AgentAssay reports
trace fingerprinting as high-power. Our `h2_phase_a1` data has five independent
runs of one task producing five distinct final states, **all accepted**. The
direct test: *does a test with more power to detect trajectory change also
have more power to report harmless change as regression?* That is an adversarial
check on their headline mechanism, and a negative result is still publishable
as a limitation of trace-based gating.

**C — Independent empirical audit.** Whether methods of this class reach the
claimed detection power and savings on a real coding agent with SWE-bench
containers. Our advantage is not breadth: it is frozen protocols, real
expensive runs, fail-closed artifacts and pre-registered stopping. Contingent
on question 1.

**D — Recoverability and controlled intervention.** C2-H forks and re-samples
from a checkpoint; AgentAssay is passive detection. The least overlap, and the
least demonstrated value — it still needs data to be worth anything.

**A and B are the strongest**, because both are questions AgentAssay's own
framing makes *harder* to ask, and both are ones our existing frozen data
already speaks to without renting anything.

## 4. Order

```
read AgentAssay against the eight questions      (zero compute)
      ↓
sound on all eight  →  drop the method paper; product, or A/B
      ↓
clear gap on 7 or 8 →  design one narrow experiment around it
      ↓
only then  →  cost model  →  decide what the first $100 buys
```

No pre-registration, no rental, and no new framework until §2 is answered.
