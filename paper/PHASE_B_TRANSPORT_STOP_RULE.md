# Infrastructure stop rule for Phase B

Frozen 2026-09-09, after arm A completed and **before any outcome was computed**.
No final state, patch or hash from any continuation has been read at the time of
writing. The rule is about transport only, and it is written down now so that
whether Phase B continues is decided by numbers fixed in advance rather than by
how the results are starting to look.

## Why a rule is needed

Arm A finished 8/8 Submitted, and inside that clean-looking result:

    333 calls, 350 attempts, 12 retried steps, rate 0.036
    A_7  32 calls, 42 attempts, 5 retried (0.156), one step took 6 attempts,
         15578 s lost to failed attempts, 377 min wall clock against a
         19.9 min arm median

A retried step is a step the model was asked to produce more than once, and the
later draw kept. This project's own measurements say the endpoint disagrees with
itself at temperature 0 — different content, different tool calls, on one shape a
different number of commands. So transport is not only costing wall clock here;
on `A_7` it changed how many times some steps were sampled. That is a threat to
treatment integrity, not a latency annoyance.

It is not yet clear which of two things `A_7` is:

    a rare outlier that arm A happened to draw, or
    transport reliability degrading as the pod session ages

Arm B answers that, and answers it without looking at a single outcome.

## The rule

Arm B runs to 8/8. The runner then **stops** — it is invoked with `--arms B` for
exactly this reason, so that finishing arm B cannot roll on into the fresh arm.
Then, on transport numbers only:

    arm-level retry rate
    runs with any retry
    maximum retries at a single step
    total seconds lost to failed attempts
    trend of retries against run index
    InternalServerError vs stream Timeout mix

**Continue to the fresh arm** if arm B shows no clear worsening: retry rate still
in the low single-digit percent, and no repeat of an `A_7`-scale failure.

**Pause Phase B** if arm B produces one or more runs with a retry rate above 10%,
a single step resampled several times over, or hours of transport stall — and
especially if the later runs are worse than the earlier ones. At that point more
continuations only add trajectories whose sampling cannot be attributed to the
history treatment rather than to transport, and the right move is to fix the
transport (direct TCP, a different provider) and collect a clean confirmatory
batch, not to spend more on a contaminated one.

## What this rule does not do

**`A_7` is not deleted.** It is part of the pre-registered experiment and it
stays. Defining a threshold now that happens to exclude the run that looks
dirtiest would be selection dressed as hygiene.

The final analysis reports three layers, all of them declared here:

    primary        every valid Submitted run, analysed in its assigned arm
    sensitivity    runs marked by whether they contain any transport retry,
                   to see whether the direction of H2 is the same in both
    clean subset   transport_retried = 0 only, reported alongside and never
                   in place of the primary

## A caution against over-reading the comparison

Phase A1 had 0 retries in 188 calls; arm B of Phase B has 12 in 333. The gap is
large but it is not yet evidence of degradation over time: Phase B continuations
carry a donor prefix and issue a different distribution of requests than a fresh
Phase A run does. Distinguishing the two would need diagnostic traffic against
the endpoint, and sending that while the experiment is running is exactly what
contaminated an earlier batch. So the question stays open, and arm B is allowed
to answer the part of it that costs nothing.
