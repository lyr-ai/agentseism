# Experiment log

Append-only. One entry per run that produced a number anyone might cite.

Template:

```text
## YYYY-MM-DD — <name>

Agent:          <agent + version/config>
Tasks:          <n, source>
Trials:         <n>
Comparator:     <outcome comparator>
Schema:         <adapter_version / feature_schema_version>
Command:        <exact command>
Artifact:       results/<file>.json

Result:         <the number(s)>
Reading:        <what it does and does not support>
```

---

## 2026-09-03 — attribution harness check (synthetic)

Agent:          `agents/synthetic.py`, 4 injection sites × 10 seeds
Tasks:          4
Trials:         8
Comparator:     exact (outcome), structured (events)
Command:        `python experiments/attribution/ground_truth.py`
Artifact:       `results/attribution_ground_truth.json`

Result:         AgentSeism 1.00 @1 / 1.00 @3; correlation 0.80 / 1.00;
                first-divergence 0.17 / 0.25; largest-diff 0.00 / 1.00;
                random 0.00 / 0.50

Reading:        The harness and the baselines run end to end, and the two naive
                trace-diff heuristics are demonstrably fooled by decoy points.
                This says nothing about real agents: the synthetic agent has one
                injected source by construction, and correlation alone nearly
                solves it. Supports no hypothesis in `claims.md`.

---

## 2026-09-03 — attribution harness, feature-projection model (synthetic)

Agent:          `agents/synthetic.py`, 4 injection sites × 10 seeds
Tasks:          4
Trials:         8
Comparator:     exact (outcome); per-feature comparators from the schema
Schema:         synthetic/1, ordered → scoring mode V × A × P
Command:        `python experiments/attribution/ground_truth.py`
Artifact:       `results/attribution_ground_truth.json`

Result:         AgentSeism 1.00 @1 / 1.00 @3; correlation 0.46 / 0.93;
                random 0.17 / 0.50; first-divergence 0.17 / 0.50;
                largest-diff 0.00 / 1.00

Reading:        Rerun of the earlier harness check under the v0.2 model, with two
                corrections that changed the numbers: the declared outcome
                observation is now rejected from every method's candidate set,
                and Attribution@k is scored as expected credit under a random
                tie-break instead of alphabetical order. Correlation-only moved
                from 0.80 to 0.46 @1 as a result — the earlier 0.80 was partly an
                artifact of the outcome observation being rankable. Still a
                synthetic agent with one injected source by construction;
                supports no hypothesis in `claims.md`.

---

## 2026-09-03 — partial-order rerun (synthetic) + stub §22 check

Agent:          `agents/synthetic.py` (4 injection sites × 10 seeds); stub ReAct
Tasks:          4 / 10
Trials:         8 / 5
Comparator:     exact (outcome); per-feature comparators from the schema
Schema:         synthetic/1 (all features positioned); react/1 (3 positioned + 3 aggregates)
Command:        `python experiments/attribution/ground_truth.py`;
                `python experiments/natural_variation/gaia_pilot.py --stub`
Artifact:       `results/attribution_ground_truth.json`, `results/gaia_pilot_stub_react.json`

Result:         Ground truth unchanged by the switch from total order to declared
                precedence: AgentSeism 1.00 @1, correlation 0.46 @1.
                On the stub ReAct agent, correlation-only reproduces the AgentSeism
                ranking in **both** scoring groups.

Reading:        Partial order did not dissolve the §22 risk, and was not expected
                to. Where the score beats correlation (synthetic), the margin comes
                from the propagation term over a real precedence chain plus local
                variation; where the schema is thin (stub ReAct), correlation is
                already sufficient. The stub is not evidence about real agents
                either way. The structural point stands: a propagation factor
                cannot answer "introduced or inherited?" — intervention can.

---

## 2026-09-04 — pilot instrumentation check (real graph, pre-pilot)

Agent:          `MarkAZhang/gaia-agent` @ `b53f536`, via `agentseism_entry:app`
Tasks:          1 (first of the frozen pilot slice, `0383a3ee`)
Trials:         2 under `gaia-mz/1`, then 3 under `gaia-mz/2`
Comparator:     exact (outcome); per-feature comparators from the schema
Schema:         `gaia-mz/1` rejected; `gaia-mz/2` adopted
Command:        `python experiments/natural_variation/gaia_pilot.py --app agentseism_entry:app
                --system-prompt agentseism_entry:build_system_prompt
                --config agentseism_entry:config --tasks 1 --trials 3`
Artifact:       `results/gaia_pilot_agentseism_entry_app.json`

Result:         Runs completed 100%; all 3 runs answered `Rockhopper penguin`,
                matching the reference. Under `gaia-mz/1`, evidence similarity
                between any two runs was 0.0 and could not have been anything
                else: the search provider stamps a per-call `request_id` UUID, a
                `response_time` float, and a per-result `id` into every response,
                and `evidence_set` compared that serialization directly. Two runs
                retrieving byte-identical documents scored 0.0, exactly as two
                runs retrieving disjoint documents did. Under `gaia-mz/2`, which
                compares canonicalized evidence content, the same synthetic pair
                scores 1.00 and the three real runs score 0.333 pairwise.

Reading:        `gaia-mz/1` is invalid for any experiment, not merely noisy:
                `evidence_set` had zero discriminating power, and as a positioned
                feature its guaranteed divergence would have propagated into the
                ranking as if it were behavior. It was rejected during the §5
                instrumentation check, before pilot data was collected, so no
                number from it has been cited. This is an instrumentation
                correction, not feature engineering against an outcome: the
                feature failed its own definition, which was checked before the
                numbers were read.

                Supports no hypothesis in `claims.md`. One task and three trials
                is a plumbing check; the identical outcome across runs says
                nothing about whether this agent varies.

Open:           `evidence_set` is keyed on canonical URL *and* normalized content,
                so the same document returned with a different snippet counts as
                different evidence. On these 3 runs that reads 0.333 for every
                pair, while URL-only identity separates them (0.500 / 0.875 /
                0.556). Whether provider snippet jitter is evidence variation or
                environment noise is unresolved, and 3 runs is too few to decide.
                Left as-is for the pilot rather than re-tuned against 3 numbers.

---

## 2026-09-04 — GAIA Level-1 pilot (benchmark selection, not a result)

Agent:          `MarkAZhang/gaia-agent` @ `b53f536`, via `agentseism_entry:app`
Tasks:          10 (frozen pilot slice, GAIA L1 validation, no attachments)
Trials:         5 (50 executions)
Comparator:     GAIA answer equivalence (outcome); per-feature from the schema
Schema:         `gaia-mz/2`
Command:        `python experiments/natural_variation/gaia_pilot.py --app agentseism_entry:app
                --system-prompt agentseism_entry:build_system_prompt
                --config agentseism_entry:config --tasks 10 --trials 5`
Artifact:       `results/gaia_pilot_agentseism_entry_app.json`
Cost:           ~$30

Result:         47 of 50 executions completed; the other 3 were cut short by the
                harness guard, not by failure. Accuracy against the GAIA
                reference 64%. Outcome varied in 3 of 10 tasks, giving 12
                outcome-differing pairs out of 89. Nine distinct loop lengths, so
                the agent is not deterministic. Intermediate variation is large
                where the outcome is stable: evidence_set local variation 0.603,
                pre_final_reasoning 0.450, while the highest outcome association
                of any feature is 0.095 against a 0.3 threshold. Variation
                survival rate 0.152. The output formatter changed the answer in
                32% of runs and *introduced* variation overall (raw answer
                consistency 0.89, formatted 0.83). AgentSeism's ranking differed
                from correlation-only in both scoring groups, so §22 did not fire
                here -- on 89 pairs that is an observation, not a comparison.

Reading:        This is a benchmark-selection experiment. It does not support or
                refute any hypothesis in `claims.md`, and the ranking numbers
                should not be cited: with 87% of pairs showing no outcome
                variation at all, "which feature relates to outcome variation" is
                a question this data is too weak to answer, and the zero
                association reflects that weakness rather than a wrong schema.

                What it does establish is about the *benchmark*: substantial
                execution variation coexists with stable outcomes on GAIA L1.
                That makes this agent a reasonable robustness case and a poor
                weak-point attribution case. Scaling the same design to 50x10
                would buy repeated observations of mostly non-varying tasks, not
                more informative ones, so it was not run. What is scarce here is
                informative tasks, not sample size.

                `variation_survival` was added for exactly this: outcome
                consistency alone cannot separate "the agent did the same thing"
                from "the agent did something different and the difference was
                absorbed". At 0.152, most execution variation on this slice dies
                before reaching the answer.

Caveats:        Data collected with the guard at 30 graph steps, which censored
                the 3 longest runs -- 2 of them in `23dd907f`, one of only three
                tasks whose outcome varied. Completed runs reached at most 27
                events, so the guard sat on the tail of the distribution: this is
                missing-not-at-random, and every length-sensitive number above
                (distinct loop lengths, execution-path variation) is biased
                downward. The guard is now 100 and censored runs are reported
                rather than dropped; any rerun should use the new value.

                Two harness defects were found by this run and fixed after it:
                `comparator_sanity` pooled feature values across tasks while
                comparing them against within-task divergences, which reported
                two sound comparators as broken; and censored runs were counted
                as failures, making the harness look 94% reliable when it had in
                fact never failed.

Identifiability:
                Per-feature amplification, added after this run, is **not
                estimable for any feature on this data: 0 of 6**. The obstacle is
                not sample size.

                `S_f = P(dY>0 | df>0)` and `A_f = S_f - P(dY>0)` are conditional
                on the feature varying, so they need pairs where it *held still*
                inside the same task to condition against. Within the three tasks
                whose outcome varies, the features that vary, vary on nearly
                every pair:

                | feature              | 23dd907f | 3cef3a44 | 46719c30 | contrast |
                |----------------------|----------|----------|----------|----------|
                | initial_plan         | 3/3      | 10/10    | 10/10    | 0        |
                | pre_final_reasoning  | 3/3      | 10/10    | 10/10    | 0        |
                | evidence_set         | 2/3      | 9/10     | 10/10    | 2        |
                | tool_call_count      | 2/3      | 8/10     | 9/10     | 4        |
                | tool_sequence        | 2/3      | 8/10     | 9/10     | 4        |
                | tool_set             | 0/3      | 6/10     | 0/10     | 17       |
                | answer_format_retries| 0/3      | 0/10     | 0/10     | --       |
                | formatter_changed    | 0/3      | 0/10     | 0/10     | --       |
                | termination          | 0/3      | 0/10     | 0/10     | --       |

                `initial_plan` and `pre_final_reasoning` have zero contrast: their
                `A_f` of +0.017 is not "absorbed", it is not estimable, and no
                number of runs creates a contrast pair. Precision is bounded by
                the smaller side, so `tool_call_count` -- 32 varying pairs against
                4 contrast pairs -- is a 4-pair estimate, not a 32-pair one.

                A second trap: pooled across tasks, `tool_call_count` and
                `tool_sequence` reach `A_f = +0.115` at `p = 0.025`, and
                `tool_set` +0.365 at `p = 0.029`, which reads as signal.
                Shuffling **within** task returns `p ~ 1.0` for every feature.
                The design is hierarchical -- task, repeated runs, pairs -- so
                pairs are not exchangeable across tasks, and outcome variation
                concentrates in three of ten. A global null destroys the level it
                needed to hold fixed, and what it then measures is task identity.

                Stated as a constraint on the method, not on this agent:
                **execution-feature amplification is estimable only where a
                feature exhibits within-task contrast; pooling pairs across tasks
                can manufacture significance by conflating task identity with
                feature-outcome association.**

Next:           Do not scale this design. GAIA L1 is retained as the
                low-variation, low-identifiability control. Benchmark B is
                selected on four criteria, the fourth added by this run:

                1. long-horizon;
                2. multiple intermediate decisions;
                3. outcome genuinely varies across repeated runs;
                4. key execution features exhibit within-task contrast --
                   repeated runs of the *same* task where a feature sometimes
                   holds and sometimes moves.

                A feature that always varies and one that never varies are
                equally unlocalizable. What carries information is recurring
                alternative execution modes on a fixed input.

---

## 2026-09-05 — evidence representation sensitivity (offline, no new runs)

Agent:          same 50 executions as the Week 1 pilot; nothing re-run
Schema:         `gaia-mz/2` unchanged -- this is a sensitivity analysis, not a
                new primary metric
Command:        `python experiments/natural_variation/evidence_representation.py`
Artifact:       `results/gaia_pilot_agentseism_entry_app_experiment.json`
Cost:           $0

Question:       `evidence_set` was not identifiable in the pilot (contrast 2 of
                23 informative pairs). Two explanations that the pilot cannot
                separate: the agent genuinely retrieves differently on every
                repeat, or the representation is fine-grained enough that a
                repeated behavior never yields a repeated observation. The first
                says change benchmark; the second says change the feature, and
                predicts that a more complex agent would hit the same wall.

Result:         Three resolutions of the same tool output, same runs, same
                comparator:

                | representation   | mean sim | varies | contrast | A_f    | p_within |
                |------------------|----------|--------|----------|--------|----------|
                | evidence_content | 0.415    | 61     | 2        | +0.029 | 1.000    |
                | evidence_source  | 0.611    | 51     | 2        | +0.061 | 1.000    |
                | evidence_domain  | 0.669    | 50     | 2        | +0.065 | 1.000    |

                Coarsening raises mean similarity by 25 points and produces no
                additional contrast. Not a thresholding artifact either: inside
                the outcome-varying tasks the similarity distribution is
                bimodal at the wrong end -- 21 of 23 pairs below 0.5, nothing
                between 0.5 and 0.9, the same 2 pairs at exactly 1.0 -- so
                counting "close enough" as held still changes nothing.

                Per task, the reason is structural:

                | | mean retrieval similarity | pairs with sim == 1 |
                |---|---|---|
                | outcome-varying tasks (3) | 0.278 | 2 of 23 |
                | outcome-stable tasks (7)  | 0.720 | 46 of 66 |

                Three tasks retrieve identically on all 10 pairs; all three have
                stable outcomes. The three tasks whose outcome moves retrieve
                something different almost every run.

Reading:        The representation hypothesis is not supported. The two
                conditions feature-level attribution requires -- a feature that
                sometimes repeats, and an outcome that sometimes moves -- are
                close to disjoint on this slice, and no re-encoding of the same
                observation creates a contrast pair out of that. It is a property
                of the slice, not of the encoding. This is the fork resolving
                toward benchmark/agent dynamics, so Benchmark B remains the next
                step rather than a feature-abstraction redesign.

                Stated carefully, because it is 10 tasks and the comparison is
                confounded with task difficulty: on this slice, retrieval
                instability and outcome instability coincide. That is consistent
                with retrieval variation driving outcome variation, and equally
                consistent with hard tasks being unstable everywhere at once.
                Separating those needs intervention, not more observation.

Caveat:         The abstraction ladder still matters for Benchmark B even though
                it did not explain this result. Contrast can be manufactured by
                coarsening until everything looks alike, and `evidence_domain`
                shows the shape of that trade: +25 points of similarity bought
                nothing here, but on a benchmark with recurring retrieval modes
                the same move would need a stopping rule. Repeatable enough to
                estimate, specific enough to keep behaviors apart.

---

## 2026-09-05 — answer-space structure (offline); supersedes the Benchmark B criteria

Agent:          same 50 executions; nothing re-run
Artifact:       `results/gaia_pilot_agentseism_entry_app_experiment.json`
Cost:           $0

Question:       Why does GAIA L1 show large execution variation and almost no
                outcome variation? Two readings: the agent is robust, or the
                tasks have an attractor strong enough that any adequate path
                lands on the same answer. These recommend opposite next steps.

Result:         Every task whose outcome stayed fixed has a single determined
                answer -- `6`, `Right`, `Wojciech`, `519`, `Rockhopper penguin`,
                `Maktay mato apple`, a logical equivalence. None of the three
                whose outcome moved does:

                | task     | answer space          | observed variation                |
                |----------|-----------------------|-----------------------------------|
                | 3cef3a44 | composable (a set)    | differ by one element (`zucchini`) |
                | 23dd907f | interpretive          | `2` vs `1` -- what counts as a stanza |
                | 46719c30 | ambiguous reference   | two different papers entirely      |

                The partition is complete on this slice: 7 of 7 stable tasks are
                single-answer, 3 of 3 varying tasks are not.

Reading:        Consistent with the attractor account, not the robustness one.
                Execution variation was never absorbed by the agent being stable;
                it was absorbed by the task having one place to land. That makes
                `variation survival = 0.152` a statement about GAIA L1's answer
                spaces at least as much as about this agent.

                Post-hoc and small: the categories above are ours, applied after
                seeing which tasks varied, over 10 tasks. It is a hypothesis the
                data is consistent with, not a test of one. Stated as a
                prediction it is falsifiable: a benchmark of single-answer tasks
                should show low outcome variation however complex its execution.

                This also explains the SWE-bench bimodality found while screening
                Benchmark B -- resolution rates pile up at 0/k and k/k. `tests
                pass` is itself a strong attractor. Long-horizon execution does
                not imply an ambiguous decision, and screening on horizon alone
                would have selected for the wrong property.

Criteria:       Benchmark B is selected on decision ambiguity first. This
                supersedes the ordering recorded in the Week 1 pilot entry:

                1. **ambiguous or underdetermined decision** -- several plausible
                   conclusions survive the available evidence, and no single
                   correct answer pulls every path back;
                2. recurring alternative modes -- the same input produces
                   execution paths that repeat, not paths that are unique every
                   time (this is what makes within-task contrast possible);
                3. measurable outcome variation across repeated runs;
                4. long-horizon execution with multiple intermediate decisions.

                Horizon moved from first to last. It is a necessary condition for
                interesting propagation, not a sufficient one, and it is the
                easiest of the four to satisfy accidentally.

Open:           Whether `outcome` should remain correctness. On a task with no
                single right answer, the quantity of interest is the decision the
                agent reached -- selected hypothesis, recommended action, risk
                level -- and "which is correct" may be unavailable and beside the
                point. The comparator contract already permits this: `outcome` is
                any value with a comparator. Nothing in the code assumes a
                reference answer exists; `accuracy` is reported as context and is
                already `None` when no reference is present.

---

## 2026-09-05 — amplification redefined as a risk difference (corrects earlier entries)

Change:         `A_f = P(dY|df) - P(dY)`  ->  `A_f = P(dY|df) - P(dY|not df)`

Why:            The marginal rate already contains the `df` arm, so it is dragged
                toward the conditional it is meant to be compared against, and a
                feature that varies often dilutes its own effect. The risk
                difference compares the two arms directly, and makes
                identifiability structural: with no contrast pairs the second arm
                does not exist and `A_f` is `None` rather than a number.

Effect on the pilot numbers, same 50 runs:

                | feature             | P(dY\|df) | P(dY\|!df) | A_f new | A_f old | contrast |
                |---------------------|-----------|------------|---------|---------|----------|
                | evidence_set        | 0.164     | 1.000      | -0.836  | +0.029  | 2        |
                | tool_call_count     | 0.250     | 1.000      | -0.750  | +0.115  | 4        |
                | tool_sequence       | 0.250     | 1.000      | -0.750  | +0.115  | 4        |
                | tool_set            | 0.500     | 0.529      | -0.029  | +0.365  | 17       |
                | initial_plan        | 0.152     | --         | None    | +0.017  | 0        |
                | pre_final_reasoning | 0.152     | --         | None    | +0.017  | 0        |

Reading:        The conclusion is unchanged -- still 0 of 6 features estimable,
                still `p ~ 1.0` under within-task permutation -- but the earlier
                numbers were more flattering than the data deserved. `P(dY|!df) =
                1.000` for `evidence_set` is two pairs in which evidence held
                still and the outcome moved both times; the marginal-baseline
                form smoothed that into a mild, plausible `+0.029`. The risk
                difference reports `-0.836` instead, which is not a finding about
                evidence but a signal that two pairs cannot support an estimate.

                A definition that produces comfortable numbers from unusable data
                is the more dangerous of the two. Every `A_f` cited in the entries
                above this one was computed under the superseded form and should
                be read as such; none of them supported a conclusion that changes.

---

## 2026-09-05 — Benchmark B step 0: open_deep_research feasibility (engineering only)

Agent:          `langchain-ai/open_deep_research` @ `1b7d2e8`
Runs:           1, reduced configuration (3 research units / 3 iterations / 5 tool
                calls, against defaults of 5 / 6 / 10)
Cost:           ~60s wall clock, roughly $0.3-0.8 by token estimate

**Not Benchmark B data.** Pre-registered as engineering calibration only: it does
not enter H1 or H2 and is not compared with GAIA.

Result:         Connecting AgentSeism to this graph needs three changes, not the
                none that was estimated from the graph structure alone.

                1. Its nodes are async-only. `stream()` exists and raises from
                   *inside* the first node rather than at the call, so the
                   adapter cannot decide on `hasattr(app, "stream")`. Fixed:
                   `astream` is used when sync capture fails that way, and
                   deliberately not by falling back to `invoke`, which would
                   silently drop stream capture on a history-rewriting graph.
                2. `research_supervisor` is a compiled subgraph; its internals
                   need `subgraphs=True` to appear at all. Not done.
                3. The trajectory recorder reads `delta["messages"]` only. Not
                   done, and the most serious of the three.

                With (1) fixed, a full run produced a 9,238-character report from
                exactly one captured node:

                    events_by_node: intake 1, final_report_generation 1,
                                    final_submission 1

                `intake` and `final_submission` are AgentSeism's own. The research
                phase ran and left no trace, because this graph carries behavior
                in `research_brief`, `supervisor_messages`, `notes` and
                `raw_notes`, and only the final node writes `messages`.

Reading:        The limitation is ours, not the agent's. Trajectory capture
                assumes LangChain-message-shaped state, which GAIA's agent
                happened to satisfy because it is a `MessagesState` graph. On a
                graph that keeps its decisions elsewhere, zero execution features
                are extractable and H2 cannot be asked at all.

                So the earlier estimate that this agent was "adapter-free" was
                wrong: it read the graph topology and not the state shape. The
                two candidates now cost about the same to reach. What separates
                them is what the work buys -- open_deep_research would still lack
                a discrete outcome afterwards, while Ambig-DS already has one and
                lacks only a published build script. Availability is the kind of
                problem an email can solve; experimental design is not.
