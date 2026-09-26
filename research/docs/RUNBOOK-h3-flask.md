# Runbook — H3 confirmatory on flask

Everything upstream is frozen. This runbook exists so the next session spends its
GPU hours on one question and not on rediscovering where things stood.

## The single goal

> An OpenAI-compatible vLLM endpoint that does **not** pass through Cloudflare's
> ~120 s HTTP timeout.

Nothing else is in scope. Streaming and the retry loop already work and are
frozen; they were how the problem was understood, not how it gets fixed. Do not
patch the Cloudflare path further.

Order of attempts, and stop at the first that holds:

1. **RunPod Direct TCP** — expose port 8000 as a TCP port rather than an HTTP
   service, and connect to `IP:port`. The Connect panel on the H2 pod offered
   only the `ssh.runpod.io` relay, which refuses port forwarding
   (`unknown channel type`), so this needs the pod configured with a TCP port
   from the start.
2. **A different provider**, if that is awkward or flaky.

### Health check before anything else

    curl $BASE/v1/models
    # a request that generates for well over 120 s must return JSON, not 524
    curl $BASE/v1/chat/completions -d '{"model":"...","messages":[...],
         "max_tokens":8000,"temperature":0}'

The second line is the whole point. On the Cloudflare path it returned 524 with a
7879-byte HTML page in 125 s while vLLM finished the request normally.

## Then, without changing anything

    serving      inference/configs/model_h2.yaml   (Qwen3.6-27B-FP8,
                 revision e89b16ebf1988b3d6befa7de50abc2d76f26eb09, 131072)
    protocol     inference/run_phase_a.sh with IID=pallets__flask-5014, RUNS=5
    gate         experiments/coding/phase_a_gate.py  -- run unmodified, verdict
                 recorded either way. H2b's F_A != F_B eligibility is **not**
                 required for H3.
    continuations experiments/coding/run_continuations.py, arms A and B, 8 each
    audit        experiments/coding/transport_audit.py --manifest ...
                 arm-level retry rate above 0.02 makes the batch transport-limited
    curves       experiments/coding/decay.py  -- frozen at d65bc6e, do not edit

**Keep the runner's full stdout.** The H2 batch piped it through a grep that kept
only lines starting with a run label, and that is why `B_1` stopping after
thirteen calls has no explanation.

## What is already decided, so it is not decided again

- `pallets__flask-5014` comes from the fallback order frozen in
  `paper/INTERVENTION_PREREG_H2.md`. It was not chosen for H3.
- The measure, its three granularities, both curves, the censoring rules and the
  summary statistics are in `paper/PREREG_H3_REPRODUCIBILITY_DECAY.md` and
  amendment H3.1. Nothing there is revisited after seeing a flask curve.
- The pytest curves in `paper/manifests/h3_pytest_exploratory.json` are
  exploratory and select nothing about the flask analysis.

## Where things stood at the checkpoint

    H2b        untested, not refuted: 15 continuations, 15 distinct final states,
               the target event never occurred
    gate       manipulation check passed hard -- 14 of 16 continuations reproduce
               their donor's next three action signatures
    H2a        uncollected; the fresh arm was stopped by the transport rule
    H3         pre-registered, analyzer frozen, exploratory pytest curves done

The exploratory shape, for orientation only: exact commands reproduce at h=1 in
7/8 and 7/7, command survival is gone by h=3, signature survival by h=8, and
pointwise signature agreement returns to 1.00 at h=12 with survival long since
zero. Whether flask does anything like this is the question.
