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

---

## 2026-09-05 — OpenRCA replication sanity (EXPLORATORY, not confirmatory)

Agent:          `OpenRCA` RCA-agent, scaffold unmodified
Model:          `gpt-4o-2024-05-13` (upstream default, verified still callable)
Temperature:    0.0 (upstream default; none of the 8 call sites overrides it)
Tasks:          1 — Bank row 6, `task_7`, selected by rule: sorted by task_index,
                the first task whose scoring points require component *and*
                reason *and* datetime. Not hand-picked.
Trials:         3
Ground truth:   `apache02` / `network packet loss` / `2021-03-06 18:52:00`
Artifacts:      `openrca/test/{result,monitor}/Bank/agent-agentseism-runA-*`
Cost:           under $1

**Exploratory.** The features below were defined *after* reading these three
trajectories, so this batch cannot also test them. A separate confirmatory batch
follows, with the definitions frozen in `agents/openrca.py` (`openrca/1`) first.

Result:         Three runs, identical scaffold, prompt, telemetry, model and
                temperature; three different diagnoses.

                | run | component | reason | datetime | score |
                |---|---|---|---|---|
                | 0 | IG01     | network packet loss  | 18:29:00 | 0.33 |
                | 1 | Tomcat02 | high JVM CPU load    | 18:30:00 | 0.00 |
                | 2 | Tomcat02 | JVM OOM Heap         | 18:30:27 | 0.00 |

                Raw code text diverged at step 1 of 1, but semantically step 1 was
                the same in all three (load `metric_container.csv`, list KPIs);
                the differences were variable names and comments. At a behavioural
                abstraction the paths separate later and unevenly:

                | feature | run 0 | run 1 | run 2 | contrast |
                |---|---|---|---|---|
                | commit_step     | 6 | 11 | 7 | both arms |
                | candidate_width | 1 | 5  | 1 | both arms |
                | telemetry_path  | metric,trace,log | metric,trace,log | metric,log | both arms |
                | service_focus   | IG01 | Tomcat02 | Tomcat02 | both arms |
                | step_count      | 7 | 10 | 8 | one arm |

Reading:        Two things this batch is good enough to establish, and one it is
                not.

                It establishes that this configuration is not deterministic. At
                temperature 0, with the diagnostic policy fixed by the scaffold's
                own prompt -- workflow, P95 heuristic, metric-then-trace-then-log
                order, localization rules -- repeated executions still reach
                different root-cause decisions. The variation is therefore not the
                agent inventing different methods; it is the same method executed
                differently.

                It establishes that within-task contrast is available here, which
                GAIA never produced on any feature. `telemetry_path` and
                `service_focus` each hold on one pair and change on the other two.

                It does not establish that any of this recurs. Three runs give
                three pairs.

Structure:      The divergence is upstream of the evidence. Runs 0 and 2 named
                their component *inside the instruction that requested the trace
                or log query* -- the component was chosen from metrics and the
                later evidence gathered to confirm it. Run 1 carried five
                candidates through both trace and log and narrowed only at step
                11. So an `evidence_set` feature would have seen this divergence
                one step after it happened and described a consequence as a cause,
                which is why the frozen features are decision-level.

                Against ground truth, this single task already shows two of the
                three variation kinds worth separating: `reason` moves between
                correct and incorrect (run 0 right, runs 1 and 2 wrong), while
                `component` moves between two different wrong answers. Neither is
                visible in a binary correct/incorrect outcome.

---

## 2026-09-05 — OpenRCA confirmatory batch (5 new runs, features frozen first)

Agent:          `OpenRCA` RCA-agent, unmodified; `gpt-4o-2024-05-13`; temperature 0
Task:           Bank row 6, `task_7` — the same task as the exploratory batch
Trials:         5, executed after `openrca/1` was committed
Schema:         `openrca/1`, frozen in `a2f9045` before these runs existed
Artifacts:      `openrca/test/{result,monitor}/Bank/agent-agentseism-confirm-*`

Questions were fixed in advance: do the commitment modes recur, does
`service_focus` recur, do `commit_step` and `candidate_width` show within-task
contrast, does the outcome keep varying, and is early commitment related to the
final answer.

Result:         | run | commit_step | candidate_width | telemetry_path | service_focus | component | reason |
                |---|---|---|---|---|---|---|
                | 0 | 8 | 2 | m>t>l | Tomcat02 | Tomcat02 | JVM OOM |
                | 1 | 6 | 1 | m>t>l>m>t>l | IG01 | Tomcat01 | JVM OOM |
                | 2 | 8 | 1 | m>t>l | Tomcat02 | Tomcat02 | JVM OOM |
                | 3 | 8 | 2 | m>t>l>m>t | IG02 | IG02 | network latency |
                | 4 | 8 | 3 | m>t>l>m>l | IG01 | IG01 | high memory usage |

                Modes recur. `service_focus` takes `Tomcat02` twice, `IG01`
                twice, `IG02` once; `commit_step` is 8 in four runs and 6 in one;
                `reason` is JVM OOM in three. The agent is not drifting through
                unique states, it is moving between a few repeated ones.

                All seven declared quantities have both arms, against zero of six
                on GAIA.

                The pre-registered early-commitment question has a shape but not
                an answer. The single run that committed at step 6 is also the
                only one whose reported component left its investigation target
                (`IG01` -> `Tomcat01`); the four that committed at step 8 all
                reported the component they had focused on. One case.

New defect:     **The outcome saturates, which is GAIA's failure mirrored.**
                Defining outcome divergence as "any of component, reason or
                datetime differs" gives `P(dY) = 1.00` over all 10 pairs, so both
                arms of every amplification are 1.00 and `A_f` is identically 0 --
                not because no feature matters but because the ruler has no
                gradations left. On `component` alone the base rate is 0.90, which
                leaves the `not dY` arm resting on a single pair;
                `telemetry_path` reports `A_f = +1.00` from that one pair, which
                is noise. `reason` and `occurrence` are better balanced at 0.70.

                So identifiability is a **two-sided** condition, and the earlier
                statement of it was half a rule:

                    a feature must sometimes vary and sometimes hold
                    **and the outcome must sometimes vary and sometimes hold**

                GAIA saturated the feature side: features always varied, leaving
                no control arm. This task saturates the outcome side: outcomes
                almost always vary, leaving no control arm at the other end.
                Neither is estimable, for the same structural reason.

Reading:        No number here should be cited; every estimate rests on one or
                two pairs. What the batch establishes is that OpenRCA clears the
                gate GAIA failed -- execution features exhibit natural within-task
                contrast and recurring modes -- and that clearing it exposes the
                symmetric constraint at the outcome end.

Next:           More tasks, not more trials on this one. Trials deepen a single
                task's pair count while leaving its outcome base rate where it is;
                tasks of differing difficulty are what supply pairs whose outcome
                held still. This is the opposite prescription from GAIA, where the
                scarcity was informative tasks rather than stable ones.

---

## 2026-09-05 — OpenRCA Bank, 8 tasks x 5 runs (DISCOVERY SET, now frozen)

Agent:          `OpenRCA` RCA-agent, unmodified; `gpt-4o-2024-05-13`; temperature 0
Tasks:          8 — the first eight `task_7` rows of Bank in file order
                (6, 8, 23, 26, 33, 35, 43, 44), fixed by rule before running
Trials:         5 each, 40 runs, 80 within-task pairs
Schema:         `openrca/1`, frozen in `a2f9045` before any of these runs
Artifacts:      `openrca/test/{result,monitor}/Bank/agent-as-b8-*`,
                `agent-as-b8clean-r23-*`

Result:         The outcome regime is mixed, which is what the batch was for.
                Per-task pair-divergence rates range 0.70–1.00 for `component`,
                0.40–1.00 for `reason`, 0.40–1.00 for `occurrence`; pooled base
                rates are 0.78 / 0.70 / 0.76. Neither margin is saturated, so
                both arms exist at the outcome end as well as the feature end.

                | Y | feature | n00 n01 n10 n11 | A_f | p_within | powered |
                |---|---|---|---|---|---|
                | component  | service_focus   | 10 1 8 61 | +0.79 | 0.000 | no |
                | component  | commit_step     | 4 6 14 56 | +0.20 | 0.191 | no |
                | component  | candidate_width | 8 17 10 45 | +0.14 | 0.311 | yes |
                | component  | telemetry_path  | 6 16 12 46 | +0.07 | 0.571 | yes |
                | reason     | commit_step     | 6 4 18 52 | +0.34 | 0.063 | no |
                | reason     | service_focus   | 5 6 19 50 | +0.18 | 0.234 | no |
                | reason     | candidate_width | 7 18 17 38 | -0.03 | 1.000 | yes |
                | reason     | telemetry_path  | 6 16 18 40 | -0.04 | 0.886 | yes |
                | occurrence | telemetry_path  | 9 13 10 48 | +0.24 | 0.027 | yes |
                | occurrence | commit_step     | 4 6 15 55 | +0.19 | 0.187 | no |
                | occurrence | service_focus   | 4 7 15 54 | +0.15 | 0.412 | no |
                | occurrence | candidate_width | 7 18 12 43 | +0.06 | 0.669 | yes |

Excluded:       `service_focus -> component` is outcome-proximal and is not a
                result. `service_focus` is the component the agent settled on
                while investigating; `component` is the component it then
                reported. They held the same value in 31 of 40 runs and moved
                together on 71 of 80 pairs. `A_f = +0.79, p < 0.001` says the
                agent reports what it decided. This is the leakage already
                recorded for declared outcome observations, one step further
                upstream. The rule is declared generally in `agents/openrca.py`:
                a feature is excluded for an outcome dimension when it is a direct
                semantic precursor or near-copy of it, per dimension rather than
                globally -- `service_focus` stays analysable against `reason` and
                `occurrence`, which it does not restate.

Reading:        Two statements, both required.

                **The benchmark works.** GAIA returned `p = 1.000` for every
                feature because its feature-held pairs all came from tasks whose
                outcome never moved, leaving nothing to condition on inside a
                task. Here the permutation p-values spread across 0.000–1.000:
                the test has power. Mixed outcome regimes across tasks are what
                supplied it.

                **The features are not established as amplification points.**
                Twelve tests were run; Bonferroni gives `alpha = 0.0042`. With
                the proximal pair excluded, nothing survives correction --
                `telemetry_path -> occurrence` at 0.027 and `commit_step ->
                reason` at 0.063 do not. Two of four features are also
                underpowered by the pre-registered threshold: `commit_step` has
                only 10 feature-held pairs against 70 feature-moved.

Discovery:      `commit_step -> reason`, `A_f = +0.34`, `p = 0.063`, underpowered.
                Suggestive and nothing more. The direction matches the mechanism
                the exploratory batch suggested -- commit early, then gather
                evidence that confirms the chosen component -- but 0.063 is not
                0.05, and adding Bank runs until it crosses would be optional
                stopping.

                **Bank is now the discovery set and is frozen.** No further Bank
                runs for this hypothesis. Confirmation requires a held-out system;
                Market and Telecom are downloaded and unextracted for exactly this.

---

## 2026-09-05 — gpt-4o-mini backbone feasibility (NO-GO)

Purpose:        Not an AgentSeism result. A bridging check on whether a cheaper
                backbone stays in the behavioural regime the study needs, after
                measured cost made the pre-registered Telecom design infeasible.
Tasks:          Bank rows 6, 8, 23 — the first three of the frozen discovery set
Model:          `gpt-4o-mini`; scaffold, prompt, temperature and task rule
                otherwise identical to the Bank runs

Accounting:     | | |
                |---|---|
                | planned | 15 |
                | attempted | 3 |
                | completed | 0 |
                | censored at the upstream 25-step budget | 3 |
                | never attempted | 12 |

                The 12 were never attempted, not lost: the upstream runner
                aborts a task's remaining repetitions after a run ends without a
                parseable answer, so a censored first run takes the other four
                with it. Reporting this as "3 of 15 completed" would imply 15
                attempts and a 20% success rate; there were 3 attempts and a 0%
                success rate, and the sampling loss is at task granularity.

Result:         Censoring 3 of 3, against a pre-declared NO-GO threshold of 30%.
                All three runs ran to 48 logged steps, saturating the budget;
                `gpt-4o` on the same three tasks ran 15–29 and never reached it.

                The mechanism is not what the first log suggested. `gpt-4o-mini`
                does name single components -- row 6 at steps 6 and 7, row 8 at
                step 10, row 23 at steps 9 and 10, comparable to `gpt-4o`'s
                commit points. What differs is that commitment does not hold: row
                6 names one component at steps 6–7, returns to multiple
                candidates at steps 8–11, and names a single one again at steps
                16–17, until the budget runs out.

                So it is not "cannot commit" but "commitment is not terminal",
                and that is the more consequential difference. `early_commit` is
                defined as the first instruction naming exactly one candidate,
                and on `gpt-4o` that event is where the investigation narrows for
                good. Here the same event is one hypothesis among several the run
                will revisit. The feature would still compute and would not
                measure the same thing.

Decision:       **NO-GO for `gpt-4o-mini` as the primary backbone**, on three
                independent grounds: censoring far past the declared threshold;
                censoring that corresponds exactly to non-convergent
                trajectories, which is MNAR on the axis being measured; and a
                primary feature whose meaning does not survive the substitution.

                The upstream 25-step budget is **not** changed. Unlike GAIA's
                recursion guard, which AgentSeism set and which sat on the tail
                of the upstream distribution, `max_step=25` is OpenRCA's own
                default in OpenRCA's own runner. Reaching it is agent behaviour
                under its intended budget, and raising it to recover data would
                change the agent being measured.

Reading:        The observation worth keeping, and worth not chasing: agent
                instability appears to change *qualitatively* with model
                capability. The stronger model varies in **when** it commits; the
                weaker one, under the same scaffold and budget, does not converge
                on a commitment at all. That is a model-comparison question and
                this project is not one, so it is recorded here and left.

---

## 2026-09-05 — Telecom confirmation: not confirmed (independent falsification)

Agent:          `OpenRCA` RCA-agent, unmodified; `gpt-4o-2024-05-13`; temperature 0
System:         Telecom, held out until this run
Tasks:          4 — rows 4, 7, 11, 12, the first four of the pool fixed by the
                original eligibility rule (`task_6` + `task_7`, file order)
Trials:         5 each, 20 runs, 40 within-task pairs, all completed
Protocol:       `paper/TELECOM_CONFIRMATORY_PROTOCOL.md`, amended to 4x5 in
                `1c74e70` before any Telecom outcome was examined
Cost:           ~$22

Extraction defect, found and fixed before the primary test:
                The first extraction produced 0 of 20 early commitments.
                Inspection showed the extractor carried Bank's component
                vocabulary -- `apache02`, `Tomcat01`, `IG01` -- while Telecom
                names hosts and containers (`os_001`, `docker_004`, `db_001`, 43
                candidates). No Bank name can appear in a Telecom instruction, so
                no commitment could ever be recognised and `early_commit` was
                False by construction. The defect is demonstrable without
                reference to any outcome value, which is the exception the
                pre-registration allows, and it was corrected -- per-system
                vocabularies transcribed from the scaffold's own prompts -- before
                the primary test was run. After correction, `early_commit` is
                True in 11 of 20 runs.

Capability:     All four tasks carry within-task contrast on the feature (2/5,
                4/5, 1/5, 4/5) and `Y_reason` divergence of 0.40–0.60. Neither
                margin saturates; the design could have detected the effect.

Primary test:   `H1: early_commit -> Y_reason`, one-sided, alpha = 0.05.

                    n00 = 13   n01 = 9   n10 = 7   n11 = 11      40 pairs
                    P(dY | df)   0.611
                    P(dY | !df)  0.409
                    A_f          +0.202        (Bank discovery: +0.34)
                    p_within     0.203         one-sided
                    powered      no  (smaller arm 18, threshold 20)

Per task:       | task | n00 n01 n10 n11 | A_f |
                |---|---|---|
                | 4  | 1 3 3 3 | -0.25 |
                | 7  | 3 3 3 1 | -0.25 |
                | 11 | 3 3 1 3 | +0.25 |
                | 12 | 6 0 0 4 | +1.00 |

Verdict:        **Not confirmed.** Directionally consistent and underpowered,
                and that is the weaker half of the reading. Two of four incidents
                run the *other* way, and the pooled `+0.202` is carried by task
                12 -- the one task where the feature and the outcome move in
                perfect lockstep, over 10 pairs.

                The conclusion is therefore not "more samples might reach
                significance" but: **there is no evidence that early commitment
                is a system-independent amplification mechanism.** Both halves
                matter. The test was underpowered; the task-level heterogeneity
                also removes the main reason to chase power.

                No fifth task is added. No intervention is implemented -- the
                commitment intervention existed to test a mechanism that
                held-out data does not support, and building it now would be
                constructing a causal test for a hypothesis that failed its
                observational confirmation.

What survives:  The falsified claim is specific: *premature commitment is the
                amplification point*. It is dropped.

                What the OpenRCA work established is not affected: repeated
                executions of a fixed policy on identical telemetry reach
                different diagnoses; execution features exhibit recurring modes
                and genuine within-task contrast, which GAIA never produced;
                large intermediate variation coexists with stable outcomes;
                outcome-proximal features leak and must be excluded per
                dimension; pooled inference measures task identity and must be
                stratified.

                It also sharpens the motivation. If one mechanism were the
                general answer, a localization method would be largely
                unnecessary -- one would simply measure that mechanism. The
                task-level heterogeneity here is the case for the method:
                **which execution decision becomes consequential appears to be
                task- and system-dependent**, which is what a discovery procedure
                is for.

Status:         OpenRCA is frozen. Market is not run. The benchmark is recorded
                as method-development and exploratory, not as the source of a
                headline mechanism.

---

## 2026-09-07 — coding divergence experiment, 10 repositories x 3 runs

Agent:          `mini-swe-agent` 2.4.6, unmodified
Model:          `Qwen/Qwen3.6-27B-FP8` @ `e89b16eb`, vLLM 0.28.0, temperature 0,
                one A40, `max_model_len` 32768
Schema:         `coding/1`, frozen in `b543af2` before any of these runs
Protocol:       `paper/CODING_EXPERIMENT_PREREG.md` with two amendments and the
                manifest, all committed before data
Runs:           30 of 30 completed, 271 minutes wall clock, ~$2.3 of GPU
Artifacts:      trajectories, probes and logs per run; analysis in
                `experiments/coding/divergence.py`

Result:         26 runs submitted a patch; 4 ended in `ContextWindowExceeded`.

                | task | pairs |
                |---|---|
                | astropy-12907 | **absorbed 3** |
                | pydata/xarray-2905 | **persistent 3** |
                | sympy-11618 | **persistent 3** |
                | matplotlib-13989 | persistent 2, absorbed 1 |
                | scikit-learn-10297 | persistent 2, absorbed 1 |
                | django-10097 | persistent 1 (two runs censored) |
                | pallets/flask-5014 | absorbed 1, unresolved 2 |
                | sphinx-10323 | absorbed 1, unresolved 2 |
                | pytest-10051 | **unresolved 3** |
                | mwaskom/seaborn-3069 | no usable pair — all three censored |

                Totals: absorbed 7, persistent 11, unresolved 7.

Empty-state defect, fixed before these numbers:
                The first pass classified 17 of 25 pairs as anomalous, which the
                pre-registration calls a measurement bug rather than a finding.
                It was one: the only state two runs shared was `sha256("")`, the
                hash of an empty diff, which every run holds before it edits
                anything. Command signatures typically diverge at step 0 or 1
                while the repository stays untouched for many steps, so every
                pair "reconverged" on having changed nothing yet. Two runs that
                have not edited the repository have not converged on a solution;
                they have not started. Reconvergence now requires a shared
                *non-empty* source state after the divergence point, and the
                unresolved count fell from 17 to 7.

The seven that remain are **not** the same kind of problem:
                They reconverge on a real state and still end with different
                patches, which is not contradictory. A pair can run

                    A: S0 -> S1 -> S2 -> S3 -> patch A
                    B: S0 -> T1 -> S2 -> T3 -> patch B

                meeting at `S2` and parting again. The pre-registered
                classification assumed that once two runs reconverge they stay
                reconverged, and agent trajectories do not oblige. So the defect
                may be in the scheme rather than the instrument, and forcing
                these into `absorbed` or `persistent` would be editing the data
                to fit the categories. They stay unresolved.

Reading:        **Interim, and deliberately weaker than "H supported".**

                The data show clear task-level heterogeneity, including tasks
                with complete absorption (astropy, 3 of 3) and tasks with
                persistent divergence (xarray and sympy, 3 of 3 each), with
                mixed tasks in between. That is the shape H predicts, and the
                pre-registered support condition is met on its face.

                But the pre-registered binary treatment of reconvergence is
                insufficient for trajectories that reconverge and then diverge
                again, and seven pairs fall there. Until those are understood at
                the representation level, "H supported" would be claiming more
                than the classification can carry.

Censoring:      `max_model_len` was set to 32768 against a model that supports
                262144, deliberately, so that the split between weights and KV
                cache would be visible on a 48 GB card. That choice censored 4
                runs, and not at random: seaborn lost all three and django two.
                Longer trajectories are the ones cut, and longer trajectories are
                plausibly the more divergent ones -- the same
                missing-not-at-random shape as GAIA's recursion guard. Any rerun
                should raise the limit, and that argument does not depend on
                these results.

Next:           Plot source-state evolution for the seven unresolved pairs before
                touching the classification. Whether they genuinely re-diverge is
                a question about trajectory topology, and if they do, "absorbed
                versus persistent" is too coarse a vocabulary. That would be a
                post-hoc observation and a next hypothesis, not a revision of the
                pre-registered one.

### Correction and re-analysis, same 30 runs

Two changes to the analysis, neither to the data.

**Outcome identity moved to the canonical source state.** The pre-registration
compared `submission` strings, and `submission` is not the object the hypothesis
is about. It is a string the agent produced, and it can carry files that are not
tracked source: sphinx r2 submitted 19,439 bytes against a 720-byte source diff,
the extra 18kB being a scratch file it had written, while all three runs of that
task ended on the identical `tracked_diff_hash` with byte-identical changes to
the single source file they touched. Counting r2 as a different solution is a
measurement error, and the mismatch is visible without reference to any result.

The pre-registered measure is **kept and reported**, not overwritten:

    F_v1   submitted patch strings equal    (pre-registered)
    F_v2   final tracked_diff_hash equal    (correction)

They disagree on 2 of 25 pairs, both sphinx.

**The label was replaced by three separate facts**, because collapsing them lost
a real topology:

    D   command-signature sequences ever differ
    R   after D, both runs hold the same non-empty tracked source state
    F   final source states equal

| topology | D | R | F | |
|---|---|---|---|---|
| absorbed | 1 | 1 | 1 | astropy 3/3, sphinx 3/3 |
| persistent | 1 | 0 | 0 | xarray 3/3, sympy 3/3 |
| **re-divergence** | 1 | **1** | **0** | **pytest 3/3**, flask 2/3 |

    v2: absorbed 9, persistent 11, re-divergence 5
    v1: absorbed 7, persistent 11, unresolved 7

The seven unresolved pairs were two different things. Two were the sphinx
construct mismatch. The other five are `D=1, R=1, F=0` -- runs that meet on a
real source state and part again -- which the pre-registered scheme could not
express because it assumed reconvergence is terminal. They are not fixed and not
forced into a category.

**Primary, pre-registered:** task-level heterogeneity, with astropy fully
absorbing and xarray and sympy fully persisting. Those three classify identically
under v1 and v2, so the finding does not rest on the correction.

**Post-hoc:** trajectories can diverge, reconverge, and diverge again, and on
pytest that is every pair rather than a stray case. Stochasticity here is not one
branch point whose effect either survives or does not; divergence appears to be
created and erased repeatedly along an execution. This was not predicted, is not
a pre-registered result, and is a hypothesis for a separate confirmation.

---

## 2026-09-07 — H2 fork machinery, validated with no model in the loop

Pre-registered in `paper/INTERVENTION_PREREG_H2.md`. Nothing here is a result
about agents; it is the check that Phase B is capable of measuring what it
claims to, run before any GPU was rented for it.

**What the intervention needs.** Two continuations that differ only in carried
context, starting from the same tracked source state. Two mechanical facts have
to hold before that sentence means anything, and both are checkable offline.

**What made it non-trivial.** At the pytest fork point the three runs held the
identical tracked source and three *different* workspaces — `test_repro.py`,
`reproduce_issue.py`, `repro.py`. So a rebuild that restores source and drops the
scratch files would satisfy the fingerprint the experiment is named after and
would silently have changed the experiment. And the primary probe stored only
hashes, which cannot be inverted, so nothing could be forked from that batch at
all: the archive layer added here keeps the bytes behind each fingerprint, and
is storage, not representation — `coding/1` is unchanged.

**The bridge.** `experiments/coding/replay.py` re-executes a recorded
trajectory's own commands with the archive on. No model call, so it costs Docker
and no GPU, and it is a check on its own premise: if replay does not reproduce
the recorded fingerprints, those states were not reachable from the commands
alone.

**Result** (`experiments/coding/fork_validation.py`, local Docker, x86 under
emulation, zero model calls, reproduced twice):

    fork point 400ed4047a82  held by {r0: step 8, r1: step 12, r2: step 10}
    donor A = r0 @ 8    donor B = r1 @ 12

    arm A   tracked 400ed4047a82   workspace bad6642622d5   prefix 18 messages
    arm B   tracked 400ed4047a82   workspace 777d3b59c758   prefix 26 messages

    PASS  source identical across arms, workspace and context arm-specific

Replay reproduced every recorded `tracked_diff_hash` for r0 steps 1–8 and r1
steps 1–12, and the workspace fingerprint at both fork points. Fresh containers
rebuilt from the archives agree on source, differ on workspace, each matching its
own donor, and carry coherent message prefixes of different lengths that both end
on an observation.

The fork point is selected by the pre-registered rule — non-empty, held by the
most runs, earliest by latest arrival — and the donors by first-arrival step
index, never by how they ended. `tests/test_fork.py` pins that rule, including
that a run which reverts and returns to a state is credited with reaching it
once: two of the three pytest runs ran `git checkout`, and dating the meeting by
a return trip would move the fork point.

Serving for Phase A is `inference/configs/model_h2.yaml`: identical to the
primary config except `max_model_len` 32768 → 131072 and `max_num_seqs` 8 → 4.
Whether the KV pool holds a 131072-token sequence on one 48 GB card is confirmed
at boot, not assumed; the recorded fallback is 65536 for every continuation
alike, never a silent per-run retry.

**Not yet run:** Phase A donors, and Phase B. No GPU has been started for H2.

---

## 2026-09-08 — H2 Phase A: donors collected, gate says UNIDENTIFIABLE, Phase B does not start

Five runs of `pytest-dev__pytest-10051`, fresh, `max_model_len` 131072, archive
on. All five completed. The gate is `experiments/coding/phase_a_gate.py`; its
report is `paper/manifests/h2_phase_a_gate_report.json`. **No manifest was
written and no GPU was spent on Phase B.**

    run        exit  steps  forks  wall(s)  ctx peak  reasoning  patch B  final
      0   Submitted     52     52     1185     65448      42318     1010  102c3fa15ba9
      1   Submitted     36     36      543     35824      19399      624  ad3317821606
      2   Submitted     37     37      397     28924      10359      772  fec3a3754204
      3   Submitted     39     39     1347     57004      37730      851  cbebb12a14c1
      4   Submitted     27     27      213     23203       4436      624  ad3317821606

    shared non-empty S  400ed4047a8253a9   first arrival {r0:9, r1:12, r2:10, r3:9, r4:8}
      arm A  r4 @ step  8   workspace ccdbd909f0d7   prefix 18 msgs   F_A ad3317821606
      arm B  r1 @ step 12   workspace 8557257177f7   prefix 26 msgs   F_B ad3317821606
      F_A == F_B ?  True

**Why this is a stop.** H2b asks how often a continuation lands on its own
donor's final state. The pre-registered donor rule takes the smallest and largest
first-arrival step, and here that is r4 at step 8 and r1 at step 12 — two runs
that end on the *same* source state. The primary measure cannot separate the arms
however many continuations are run.

**The pair was not reselected and will not be.** Four distinct final states exist
among the five runs, so a different pair would be identifiable, and picking it
after seeing that the rule's pair is not is choosing a comparison by how well it
separates. That is the failure mode the manifest exists to prevent, arriving one
step earlier than expected.

**Two things worth recording, neither of them a test.**

*The attractor replicates, exactly.* All five Phase A runs pass through
`400ed4047a8253a9…`, the identical hash the three primary-batch runs passed
through at a quarter of the context length. Eight independent runs, two batches,
two serving configurations, one shared intermediate state.

*The endpoints do not.* Seven distinct final states across those eight runs, and
**zero overlap between the batches** — the primary batch's three
(`5c9780ad`, `0311c057`, `b387c8a3`) and Phase A's four (`102c3fa1`, `ad331782`,
`fec3a375`, `cbebb12a`) are disjoint. The convergence point is reproducible
across serving configurations; the repair is not reproducible even within one.

This is a descriptive replication of the re-divergence topology on independent
data. It is not a pre-registered test of it: these runs were collected to
generate donors, and reporting them as confirmation of a hypothesis they were not
registered to test would be the same move in a different coat.

**The 128k change earned its place.** Two of the five runs peaked at 65,448 and
57,004 prompt tokens. Both would have hit `ContextWindowExceeded` at the primary
experiment's 32768 and been lost, as four primary runs were.

**Resolved by amendment H2.1, same day.** The donor rule selects on arrival step,
which says nothing about where the two runs end, while the primary contrast
requires different endpoints. Donor eligibility becomes a property of the pair —
both `Submitted`, both reaching `S`, and `F_A != F_B` — with the original
arrival-step tie-break applied only among eligible pairs, and the rule for `S`
itself unchanged. The estimand narrows accordingly and the amendment says so.

**These five runs are frozen out as Phase A0, design-discovery.** Four distinct
endpoints exist among them, so an eligible pair could be drawn under the new
rule; that is why it will not be. A0 supplies no donor and no confirmatory
number. Phase A1 is five fresh runs, and there is no third attempt: a second
`UNIDENTIFIABLE` stops the experiment on this task rather than buying another
batch.

---

## 2026-09-08 — Phase A1, first attempt, aborted by the endpoint being stopped

Not a result. Recorded so that tomorrow's Phase A1 is legible as the second
attempt rather than the first.

    r0  2281s  Submitted        724 B  42 calls  forkpoints=41
    r1   409s  NotFoundError      0 B  21 calls  forkpoints=20
    r2    12s  NotFoundError      0 B   1 call
    r3     5s  NotFoundError      0 B   1 call
    r4     6s  NotFoundError      0 B   1 call

The pod was stopped deliberately, to avoid paying for an idle GPU overnight, and
r1 through r4 are the endpoint disappearing underneath the runner. `NotFoundError`
is infrastructure, and the pre-registration says such a run is rerun with both
attempts recorded.

**The gate was never run on this batch, and r0 was never compared with anything.**
The decision to discard was taken before any donor could be selected, on a
billing argument that has nothing to do with what the runs contain.

r0 completed and is valid on its own terms. It is discarded anyway, and the
reason is homogeneity rather than thrift: the stochasticity this experiment
studies comes from the serving stack, so a batch assembled across two pod
sessions — two physical cards, two schedulers — has a stack change inside it.
That is the same contamination the decision to run sequentially rather than
concurrently was meant to avoid, and it would be inconsistent to accept it here.

The batch is kept at `runs/h2_phase_a1_aborted_2026-09-08`. Phase A1 proper is
five runs in one uninterrupted pod session.

---

## 2026-09-08 — HTTP 524: a transport timeout that looks exactly like model instability

Two Phase A1 attempts died before this was understood, and the misdiagnosis is
the point of the entry. Agent steps hung for 5, 8, 46 minutes. The endpoint
answered `/v1/models` in half a second throughout. It read as a flaky model
server.

**It was not.** Every hypothesis that sounded plausible was measured and rejected:

| hypothesis | measurement | verdict |
|---|---|---|
| container commands stall the connection | command+probe time: median 0.7 s, max 1.7 s, none over 60 s in any run | rejected |
| idle keep-alive connections are killed | same pooled connection after 0 s / 45 s / 90 s idle: 0.7 s, 0.7 s, 0.5 s | rejected |
| large request bodies break the proxy | 1.9 KB → 0.5 s, 28 KB → 2.5 s, 116 KB → 8.1 s, 234 KB (53k tokens) → 13.0 s | rejected |
| vLLM stalls or aborts | 0 aborts, 0 errors, 0 preemptions; all requests ≤240 s server-side; `num_requests_running` = 0 during every observed stall | rejected |

The captured response settled it:

    real agent request (293 KB)     524 in 125.8 s  text/html  7879 B error page
    tiny prompt, max_tokens 8000    524 in 125.1 s  text/html  same page
    tiny prompt, max_tokens 200     200 in   4.7 s  application/json

**HTTP 524 is Cloudflare's timeout, and RunPod's HTTP endpoint sits behind it.**
The second row is what makes the diagnosis clean: a *tiny* prompt, killed at the
same 125 s, so the boundary is elapsed time and nothing else — not body size,
not context length, not tools, not connection reuse. A non-streaming completion
sends no bytes until its last token, so any model call longer than the window
dies in transit while vLLM finishes it normally and records no error at all.

**It had been happening all along.** Maximum single model call per run:

    A0 r0 105.8 s   A0 r1 86.7 s   A0 r2 60.1 s   A0 r3 409.2 s   A0 r4 23.7 s
    A1 r0 389.9 s   A1 r1 2839.2 s

A0 r3 crossed the window once — 409 s ≈ three 125 s attempts — and that is the
run recorded the day before as "anomalously long (1347 s)" without explanation.
A0 r0's 105.8 s missed the cliff by fifteen seconds. **The batch that produced
the `UNIDENTIFIABLE` gate result was passing by luck**, and an earlier claim in
this log that the failure was specific to the second pod is withdrawn.

### The fix, and what licenses calling it transport-only

Streaming. The first chunk arrives immediately, so the window never opens.
Rejected alternative: capping `max_tokens` to fit generation inside 120 s, which
would truncate the agent's reasoning and change the object of study.

`experiments/coding/stream_equivalence.py` is the gate, and it needed two
corrections before it meant anything.

*It had no power.* Run unseeded, the server disagrees with **itself**: two
identical non-streaming requests differ in `content`, `reasoning`, `tool_calls`,
`completion_tokens`, and on the parallel-tool-call shape even in `n_tool_calls` —
the agent is handed a different number of commands to run. With a baseline that
noisy, "streaming changed nothing beyond baseline" is true no matter what
streaming does. Fixing the seed collapses it to nothing, and only then does the
comparison decide anything. (The unseeded numbers are kept: they are a direct
measurement of the serving-level nondeterminism this project assumes exists, and
seeding suppressing it locates that nondeterminism in the sampling path.)

*It compared a volatile field.* `actions` carries `tool_call_id`, minted per
response, so two byte-identical responses always differed there and two shapes
were reported unprovable. The id is excluded now, as it already was for
`tool_calls[].id`.

Result, seeded, on plain text / one tool call / parallel tool calls / long
reasoning: baseline empty and streaming empty on all four. Every field the agent
consumes — `finish_reason`, `content`, `reasoning`, tool call type, name and
JSON-parsed arguments, their order and count, `actions`, token counts — is
byte-identical streamed and unstreamed.

**Stated limitation:** the gate cannot check generations longer than the
Cloudflare window, because the non-streaming control cannot complete there. Every
shape is capped at 1500 tokens. Equivalence beyond that is extrapolation. An
uncapped first draft proved this the expensive way, spending 71 minutes
reproducing the bug it exists to work around.

### Consequence for the experiment

A retried step is **a fresh sample, not a replay**: this project's premise is
that temperature 0 leaves serving-level nondeterminism, which the unseeded
baseline above measures directly. So the retry loop moved into
`agents/coding/instrumented_model.py`, litellm is set to `num_retries: 0`, and
every attempt is numbered, timed and recorded with its exception type. Each step
carries `transport_attempts`, `transport_retried` and `transport_events`. A batch
with few retries can treat this as a nuisance covariate; a batch with many cannot
claim its steps came from the same process as unretried ones.

Both aborted A1 attempts stay `infrastructure-invalid`. A1 proper is five fresh
runs with streaming on.

---

## 2026-09-08 — Phase A1: QUALIFIED, and the attractor holds across three batches

Five fresh runs, streaming, one uninterrupted pod session. All five completed.

    run        exit  steps  wall(s)  ctx peak  reasoning  patch B  final
      0   Submitted     31      977    36837      18706      844  ed135952e20c
      1   Submitted     41     3110    62736      40656     1232  901cfacceed3
      2   Submitted     33      479    31967      15556      979  687e8628805f
      3   Submitted     47      444    35034      10797     1942  5ece9b7438d7
      4   Submitted     31      261    21834       6642      691  5b38138161e5

**Transport audit: 188 calls, 188 attempts, 0 retried steps.** Under
non-streaming the same task produced stalls of 285 s, 391 s, 626 s and 2839 s.
The prediction made when streaming was adopted — that the stalls were
non-streaming duration crossing Cloudflare's window, not the model or the server
— was specific and falsifiable, and it held. Every step in this batch is a
single draw, so the retry marks are recorded and carry no weight in analysis.

    shared non-empty S  400ed4047a8253a9   first arrival {r0:8, r1:9, r3:10, r4:10}
      arm A  r0 @ 8    workspace 8557257177f7   prefix 18 msgs   F_A ed135952e20c
      arm B  r3 @ 10   workspace bad6642622d5   prefix 22 msgs   F_B 5ece9b7438d7
      F_A != F_B       rebuild verified on both arms
      continuation step limit 240, identical for A, B and fresh

Donors are r0 and r3 under amendment H2.1: all four carriers end on distinct
states, so every pair is eligible, and the tie-break takes the widest arrival
spread (8 against 10) and then the lower run id. The selection read arrival steps
only; eligibility was the sole place a final state was consulted, and it asks
whether they differ, never which is which.

### The attractor, three batches in

    primary (32k, non-streaming)   3 runs, 3/3 reach 400ed404…, 3 distinct finals
    A0      (128k, non-streaming)  5 runs, 5/5 reach 400ed404…, 4 distinct finals
    A1      (128k, streaming)      5 runs, 4/5 reach 400ed404…, 5 distinct finals

Twelve of thirteen independent runs pass through the byte-identical non-empty
source state — the one-line `self.records = []` → `self.records.clear()` — across
two context lengths and two transport paths, and then produce twelve distinct
final patches, with no final state repeated between batches.

This is descriptive. These runs were collected to generate donors, and none of
the three batches was registered as a test of the topology. What it licenses is a
statement about stability of the observation, not a confirmation of the
hypothesis: whatever drives runs to that state is robust to changes in serving
that visibly change everything downstream of it.

Phase B may now start. The manifest is frozen at
`paper/manifests/h2_phase_a1.json`.

---

## 2026-09-09 — Phase B arms A and B: the transport stop rule fires, fresh arm paused

Transport only. **No outcome was computed**: no final state, hash or patch from
any continuation has been read. The rule applied here was frozen in
`paper/PHASE_B_TRANSPORT_STOP_RULE.md` and committed before these numbers
existed.

    arm  calls  retried   rate  runs w/ retry  max attempts@1 step  lost   exceptions
     A     269       12  0.045            5/8                    6  4.8 h  Timeout 11, ISE 6
     B     303       19  0.063            5/8                    3  3.7 h  Timeout 19, ISE 3

    per-run retry rate by index
     A   0.029  0.062  0.044  0.000  0.000  0.000  0.061  0.208
     B   0.000  0.000  0.040  0.000  0.038  0.118  0.097  0.085

**The denominator was wrong before this entry and the correction makes it
worse.** A continuation's messages open with its donor's prefix, which contains
the donor's own assistant turns — eight for arm A, ten for arm B — and counting
them credited this batch with Phase A1's steps. Arm A was reported at 0.036; on
its own calls it is 0.045. `experiments/coding/transport_audit.py` now reads the
prefix length from the frozen manifest.

### The rule fires

Written before the data: pause if arm B produces a run above 10 % retry, a step
resampled several times over, or hours of stall — **especially if later runs are
worse**.

    B_5   0.118, above the 10 % clause, 6515 s lost
    trend the three worst runs in arm B are its last three
    arm   0.045 -> 0.063

Two sub-criteria moved the other way and that is recorded rather than buried:
arm B's worst single step took 3 attempts against arm A's 6, and it lost 3.7
hours against 4.8. The rule is disjunctive and `B_5` satisfies its first clause,
so **the fresh arm does not run.** Applying it as written is the only thing that
makes having written it worth anything.

The exception mix also changed: arm B is 19 stream `Timeout` against 3
`InternalServerError`, where arm A was 11 against 6. Streams breaking
mid-generation, not connections refused at setup.

### What this does and does not block

The fresh arm serves **H2a**, whether abandoning `S` is state-carried. That is
paused.

**H2b's primary contrast needs only arms A and B**, and both are collected: 8
and 7 usable continuations. Pausing costs the third arm, not the primary
comparison. Whether those 15 support an analysis is a separate question the
three declared layers — all runs, split by retry, retry-free subset — exist to
answer, and it is not answered here.

### `B_1`, unexplained

Thirteen own calls, zero retries, ends on an ordinary observation, no exit
status, no exception recorded, and the runner printed no line for it.

**The evidence for why may have been destroyed by the way the batch was run.**
The runner's stdout was piped through `grep -E "^(A|B|fresh)_[0-9]"`, so any
traceback or diagnostic that did not begin with a run label was discarded. That
is a self-inflicted gap: a filter meant to keep progress readable also threw away
the only record of a failure. Future batches keep the full stdout.

`B_1` is therefore neither classified as infrastructure nor as data. It is left
out of arm B's seven usable continuations and recorded as unexplained.

---

## 2026-09-09 — H2b: a degenerate null, and a manipulation check that makes it mean something

First unblinding of Phase B outcomes. The three layers were declared before any
final state was read and computed in one pass by
`experiments/coding/h2b_analysis.py`.

    arm A  collected 8   usable 8
    arm B  collected 8   usable 7      B_1 excluded, unexplained
    fresh  collected 0                 stop rule

    match F_A    A 0/8 = 0.000   B 0/7 = 0.000   diff +0.000   p = 1.0
    match F_B    A 0/8 = 0.000   B 0/7 = 0.000   diff +0.000   p = 1.0
    neither donor's final state: 15 of 15
    retry-free subset (3 A, 2 B): same, 0 and 0
    hunk-location secondary:      same, 0 and 0

**Fifteen continuations produced fifteen distinct final states.** The primary
statistic is `P(F_A|A) − P(F_A|B)` and the event never occurs in either arm, so
the contrast has no variance to explain. **This is not evidence against H2b.** It
is a measure with no power on this system, and reporting it as a refutation would
be a different error from p-hacking but an error of the same family.

### The pre-registered gate is what makes the null readable

    arm A   6 of 8 continuations reproduce donor r0's next 3 command signatures
    arm B   8 of 8 reproduce donor r3's

    ['sed:-n', 'python:-m,-v', 'cat:heredoc,redirect']

Fourteen of sixteen retrace their donor exactly for three steps. The fork puts
the agent where it claims to, the containers are right, the prefixes are right,
and the null is a fact about the system rather than about the apparatus. That
distinction was written down in the pre-registration before either reading was
available, and it is the reason this batch is interpretable at all.

### What the two results say together

    short horizon   context determines behaviour exactly: 14/16 retrace 3 steps
    long horizon    context determines nothing measurable: 0/15 reach the target,
                    including 0/8 where the context is the target's own

Arm A continuations carry donor A's complete state and complete transcript. They
are replays of donor A from step 8, at temperature 0, and not one reproduces
donor A's patch. The repair phase downstream of the shared state is close to
maximally stochastic: fifteen draws, fifteen outcomes.

This also explains, rather than adds to, the earlier observation that twelve of
thirteen runs across three batches reached the identical intermediate state and
produced twelve distinct finals. It was never a fact about batches or serving
configurations. It is what this task's repair phase does.

### What follows, and what does not

**H2b is untested, not refuted.** Whether carried context biases the repair is a
question an outcome-identity estimand cannot ask here, because outcome identity
is an event of probability approximately zero. A distributional estimand — are
arm A's outcomes more similar to `F_A` than arm B's, under some graded measure —
might have power, and proposing one now, after seeing that the identity measure
returned nothing, would be choosing an analysis by its prospects. It belongs in a
separate pre-registration with its measure fixed in advance.

**H2a is uncollected.** The fresh arm was stopped by the transport rule.

The apparatus works. The fork is verified mechanically and now behaviourally.
What is missing is an estimand matched to a system whose outcome space is this
wide.

---

## 2026-09-10 — Direct TCP fails differently, and the fix is to delete the network

The flask batch was not collected. `inference/transport_gate.py` refused the
endpoint, and the reason changes what the earlier diagnosis is allowed to claim.

A pod was rebuilt with port 8000 exposed as a **TCP** port rather than an HTTP
service, so nothing passes through Cloudflare. Measured from the same client:

    2000 tok, non-streamed   200        9 KB   41.0 s   ok
    2000 tok, streamed       ttfb 0.2s  447 KB 40.9 s   ok
    8000 tok, streamed       FAIL       1463 s          ReadTimeout

    5000 tok, streamed, three times -- the largest single completion anywhere
    in the H2 data was 4954 tokens, so this is the observed worst case:
      run 0  FAIL   382.2 s   466 KB in   worst gap 0.4 s   ReadTimeout
      run 1  ok     102.5 s  1123 KB      worst gap 0.2 s
      run 2  FAIL    96.3 s   889 KB in   worst gap 0.2 s   RemoteProtocolError

**Two of three fail on the realistic worst case.** Run 1 is what healthy looks
like — 102.5 s is exactly 5000 tokens at the 49 tok/s this endpoint sustains —
so the failures are not throughput limits. They are connections dying: run 0's
apparent 7 tok/s was a dying stream dribbling, not throttling.

**Direct TCP did not solve the problem, it changed its shape.** Cloudflare
returned 524 with an HTML page, which is at least legible. This path fails
silently, sometimes as a read timeout and sometimes as a protocol error, and
succeeds a third of the time. Intermittent failure is worse for an experiment
than systematic failure: it leaves holes that cannot be attributed. The
distinction matters for anyone reading the earlier entry as "Cloudflare was the
bug" — the bug is the wide-area path, and Cloudflare was one way it showed.

### The response is to remove the path, not to try a third one

Every model step sends the whole transcript across the public internet and
streams megabytes of SSE back, because the agent and its Docker sandboxes run on
a laptop and the model runs in a datacentre. That link is now part of the
experimental system and it is not what is being studied. A third region would be
a bet on the next path being better.

The migration is to a GPU VM with root and Docker, running vLLM, the SWE-bench
containers and the agent on one host, with `OPENAI_API_BASE=http://127.0.0.1:8000/v1`.
The requirement is not a provider, it is that Docker and vLLM can share a host.

`inference/vm_gate.sh` is the gate: the card, `docker run hello-world`, disk,
the endpoint checks over localhost, and the observed worst case three times. It
keeps the 8000-token test deliberately. **If that collapses over localhost too,
the diagnosis above is wrong** and the throughput problem was never the network
— which is worth discovering in a gate rather than inside the confirmatory batch.

Cost note, since the migration looks more expensive per hour: `A_7` alone spent
4.3 hours waiting on failed transport attempts. Cheap GPU-hours are not cheap
when they are spent on a broken link.

---

## 2026-09-12 — Correctness labels: the variation is consequential

**Exploratory.** No pre-registration covers correctness — it was not part of the
coding experiment, of H2 or of H3. Everything here is hypothesis-generating.

Before the labels: a note on what is no longer available. A temp cleaner removed
the primary 30-run experiment's trajectories and batch A0's while leaving their
directories, so the cross-task correctness table this step was meant to produce
cannot be built. What survives is twenty submitted runs of
`pytest-dev__pytest-10051`, now in `data/runs/` rather than in scratch.

Evaluated with the official SWE-bench harness (5.0.2,
`SWE-bench/SWE-bench_Verified`), one evaluation per run because predictions are
keyed by instance and these are twenty runs of one instance.

    batch  run   role       steps         final  patch B  correct
    a1     r0    donor A       31  ed135952e20c      843  PASS
    a1     r1                  41  901cfacceed3     1229  PASS
    a1     r2                  33  687e8628805f      978  PASS
    a1     r3    donor B       47  5ece9b7438d7     1939  PASS
    a1     r4                  31  5b38138161e5      690  FAIL
    b      A_0   fork A        33  8d1db73994d7      567  PASS
    b      A_1   fork A        31  74f7c2cc1bc7     1361  PASS
    b      A_2   fork A        44  57d9a65e02a9     1920  PASS
    b      A_3   fork A        28  31912371fe29      709  FAIL
    b      A_4   fork A        23  8d1db73994d7      567  PASS
    b      A_5   fork A        47  11ce8fce3df2     2456  PASS
    b      A_6   fork A        32  2bb44b683d9c      629  FAIL
    b      A_7   fork A        23  8c81d60d75ee      388  PASS
    b      B_0   fork B        32  ad3317821606      623  FAIL
    b      B_2   fork B        24  f828205d0ea2      900  PASS
    b      B_3   fork B        35  4d6cea9d7d54     1125  PASS
    b      B_4   fork B        25  7a9b3555f5a5      991  PASS
    b      B_5   fork B        67  bacc5bb7e7d8     1674  PASS
    b      B_6   fork B        30  b7c0b5eebc09      999  PASS
    b      B_7   fork B        70  65a33bc84a69     1295  PASS

    overall  16/20 correct · 19 distinct final states · MIXED CORRECTNESS

### The variation is consequential

Same task, same model, temperature 0, and the outcome differs. That is the
question this project has been circling since the GAIA null, and it now has an
answer on real data: **a different ending is sometimes a wrong ending.**

### And the first quantitative answer about *where*

```text
A1, fresh runs                      4/5   = 80%
continuations from a correct donor  12/15 = 80%
    arm A  6/8   (donor r0 PASS, forked at step 8)
    arm B  6/7   (donor r3 PASS, forked at step 10)
```

Both donors were correct. Continuations carry the donor's exact tracked source,
its scratch files and its full transcript — and succeed at the rate of a run
started from nothing.

> **The first eight to ten steps carry no detectable information about whether
> the run will be correct.**

Which is a direct, negative answer to *where should a steering intervention go*:
not there. Whatever makes a run fail happens later, and a fork point chosen
because it is a convenient shared state is not chosen where the outcome is
decided.

**Stated with its power.** Twenty runs cannot separate 80% from 75%. The honest
claim is that no *large* effect is detectable, not that the effect is zero. What
the sample does support is the negative design implication: a steering point at
step 8 would have nothing to act on.

### Two observations not to over-read

`A_0` and `A_4` reached the byte-identical final state `8d1db739…` (567 bytes),
the first terminal reconvergence in this dataset. Both correct.

Patch size looks like a predictor and is not: the four failures are 690, 709,
629 and 623 bytes, but passes include 388 and two of 567. With four failures,
any rule fitted here is noise.

### What this unblocks and what it does not

Unblocked: the project can now ask which variation matters rather than only
where variation exists. Eligibility for the next stage changes from *interesting
topology* to **outcome variance**, and this task has it.

Not unblocked: one task, one model, and a base failure rate of 20% means a
future intervention experiment needs a much larger sample to detect a change in
it. Four failures is enough to establish that failures exist and not enough to
characterise them.

---

## 2026-09-12 — Exploratory C1: aligning passing and failing runs

**Post-hoc on four failures.** Nothing below is a finding. The output is a list
of candidate signals and a candidate horizon, to be fixed in advance and tested
on runs that are not these.

Features are mechanical — rules over the command string, the probe's state
hashes and the observation text (`experiments/coding/step_features.py`). No step
asks a model what a trajectory was trying to do, because with four failures a
free-form comparison produces a persuasive story about noise.

### A correction that changed the answer

The first alignment put continuation step 1 next to fresh-run step 1. A
continuation's first step is absolutely step 9 or 11 — it inherited everything
before that from its donor — so that comparison put a run with two edits behind
it next to one with none, for fifteen of the twenty runs. Donor prefixes are now
prepended and the cumulative counters carry the inherited work.

It moved the apparent separation from step 5 to step 13–14.

### The sample is smaller than it looks

```text
h=5    20 runs at risk    7 distinct histories
h=8    20                 7
h=10   20                14
h=12   20                20
```

Before step 10, fifteen of the twenty runs share one of **two** prefixes. Any
early-horizon signal computed over twenty runs is pseudo-replication, and the
first version of this analysis reported exactly that. **This dataset cannot
answer the early-horizon question**, whatever the plots suggest.

### Totals at end of run

    feature                     PASS mean  FAIL mean    delta
    cum_edits                         9.4        6.0     -3.4
    cum_reverts                       2.0        1.0     -1.0
    distinct_states                   3.7        2.8     -0.9
    diff_bytes                     1202.0      662.8   -539.2
    cum_tests                        11.8       10.8     -1.1
    cum_suite_tests                   4.6        4.5     -0.1
    cum_failing_tests                 3.1        3.2     +0.2

### Candidate signals — all exploratory

The coherent reading is that **failing runs iterate less on the source while
seeing the same evidence**: fewer edits, fewer reverts, fewer distinct states, a
smaller final patch, and the same number of suite runs and observed test
failures.

| candidate | direction | earliest persistent separation | caution |
|---|---|---|---|
| cumulative source edits | FAIL fewer | **h ≈ 14** | strongest and most persistent |
| final patch size | FAIL smaller | h ≈ 13 | passes include 388 and 567 bytes |
| cumulative reverts | FAIL fewer | h ≈ 16, unstable | flips sign twice |
| distinct source states | FAIL fewer | no clean horizon | |
| suite test runs | FAIL more | h ≈ 13 | equal by end of run |
| observed test failures | FAIL more | h ≈ 10 | inside the pseudo-replicated zone |

The last row is the one to distrust most: its separation begins where the
sample is still effectively seven trajectories.

### Candidate horizon

**h ≈ 14**, where cumulative edits separate and stay separated. Runs have a
median length of 32–33 steps, so that is around 40% of the way through — inside
the window where an intervention would still have somewhere to go.

That is the good case for the steering hypothesis, and it is a hypothesis. With
four failures the horizon could move substantially on the next twenty runs.

### What this says about the next batch

Do **not** infer the sample size from the 20% failure rate alone. The design
question is not "how many failures do we need to describe" but "how large is the
effect we have pre-committed to detecting" — and that effect is now nameable:

> a difference in cumulative source edits at h = 14

Fix that one feature, its direction and its horizon in a pre-registration, then
size the batch for it. Collecting a hundred runs first and searching them again
would repeat the mistake this section exists to avoid.

One further requirement the pseudo-replication makes explicit: the next batch
needs **independent runs, not continuations of a shared prefix**, or the early
horizons will be unanalysable again.

`paper/figures/outcome_alignment.svg` shows all twenty on absolute steps, with
the pseudo-replicated zone shaded and the candidate horizon marked.
