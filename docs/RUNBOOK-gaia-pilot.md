# Runbook — GAIA pilot (Week 1)

Target agent: **github.com/MarkAZhang/gaia-agent** — LangGraph, multi-node,
evaluated on GAIA Level 1 validation (41/53, ~19.9 turns per task).

Goal: **10 tasks × 5 trials**, then read the five go/no-go checks. Nothing else.

## What it costs

From that repository's own reported eval numbers:

| | per run | pilot (50 runs) | full slice (500 runs) |
|---|---|---|---|
| cost | $0.61 | **~$30** | ~$305 |
| latency | 76 s | ~65 min serial | ~10.5 h serial |
| turns | 19.9 | — | — |

The pilot exists so that a bad answer to "is there a phenomenon here?" costs $30
rather than $305. Do not skip it.

## 1. GAIA access

The dataset is gated on Hugging Face — accept the terms once, per account:

1. Log in at <https://huggingface.co/datasets/gaia-benchmark/GAIA> and agree to
   the conditions (gating exists to limit scraping and contamination).
2. `huggingface-cli login` locally, so `datasets` can read it.
3. Use the **validation** split. Test-split answers are private.

`benchmarks/gaia.py` stores only task ids, never dataset content.

## 2. The agent

```bash
git clone https://github.com/MarkAZhang/gaia-agent
cd gaia-agent && uv sync           # or pip install -r requirements.txt
cp .env.example .env               # then fill in the keys
```

Keys it needs: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (output formatter),
`GEMINI_API_KEY` (image analyzer), `TAVILY_API_KEY` (search), `E2B_API_KEY`
(code sandbox). LangSmith tracing is optional and irrelevant to us — AgentSeism
captures its own trace.

Run one Level-1 question first, their way, before involving AgentSeism. If that
does not work, nothing downstream is worth debugging.

## 3. Expose the graph

AgentSeism needs the compiled graph and the repo's own system prompt. A five-line
module inside their checkout is enough:

```python
# gaia-agent/agentseism_entry.py
from agent_graph.build_agent_graph_and_config import build_agent_graph_and_config
from agent_graph.build_system_prompt import build_system_prompt  # noqa: F401

app = build_agent_graph_and_config().graph
```

Pass their `build_system_prompt` explicitly. Running their agent under a generic
prompt measures a different agent than the one whose numbers you are citing.

## 4. Run the pilot

```bash
cd /path/to/agentseism
PYTHONPATH=/path/to/gaia-agent/src:/path/to/gaia-agent \
python experiments/natural_variation/gaia_pilot.py \
    --app agentseism_entry:app \
    --system-prompt agentseism_entry:build_system_prompt \
    --adapter gaia-graph \
    --tasks 10 --trials 5
```

Offline plumbing check, no keys, no cost:

```bash
python experiments/natural_variation/gaia_pilot.py --stub
```

## 5. Read the checks

| check | what a bad value means |
|---|---|
| runs completed | harness or rate limits, not the agent — fix first |
| runs with every feature | the projection is losing part of the execution |
| distinct loop lengths | agent may be too deterministic to study |
| tasks with variation | no RQ1 phenomenon on this agent |
| features tied to the outcome | the feature schema is wrong for this agent |
| noisy but inconsequential | **none is bad**: without a feature that varies a lot and matters little, the ranking may just be tracking whatever changes most |
| correlation comparison | if correlation-only reproduces the ranking, §22 has fired |

The script prints `VERDICT: proceed to 50 x 10` only if every check passes.

## 6. Then stop and decide

Scale to 50 × 10 only on a passing verdict. If the verdict fails, the finding is
about *this agent* — record it in `paper/experiments.md` and pick the next agent,
rather than tuning the schema until the numbers look better. The schema is frozen
per adapter version for exactly this reason; changing it means a new version and
a rerun.

## Adapter notes specific to this agent

- **Stream capture is mandatory.** Its `memory_management` node overwrites
  earlier tool results with `"removed"` to save input tokens. Reading the
  trajectory from the final state would report the agent as having gathered
  almost no evidence. The adapter refuses to project a final-state-only trace.
- **Two answers exist.** The agent's own `Ans:` line and the `output_formatter`
  rewrite are both declared outcome observations; `formatter_changed_answer`
  carries the rankable part, so a formatting rewrite is never counted as agent
  variation.
- **Runs can end without an answer.** Refusal and tool-not-available are
  terminal nodes, recorded in the `termination` feature.
- **Retries are visible.** `answer_format_retries` counts how often
  `check_and_get_final_answer` rejected the format and looped back.
