# Runbook — C2 recoverability, on a colocated GPU VM

C2 is frozen. Nothing in this runbook is a decision: the horizons, the
trajectories, the replication counts and the stopping rules are already
registered in `paper/PREREG_C2_RECOVERABILITY.md` (+ amendments C2.1, C2.2) and
turned into data in `experiments/coding/c2_protocol.py`.

```
protocol hash   0fafa0a2534272a6
horizons        16, 24, 28
FAIL arm        r4, A_3, A_6, B_0    × 4 replicates
PASS arm        r0, r1, r2, r3       × 2 replicates
total           72 continuations
```

If the protocol hash printed by the runner is not `0fafa0a2534272a6`, the plan
has changed and this runbook does not apply.

---

## 0. What the host has to be, and why

The agent, the SWE-bench containers and vLLM must be **on the same host**. This
is the point of the migration, not a convenience: two RunPod network paths
failed in two different ways (HTTP proxy — Cloudflare 524 on any non-streaming
call past ~120 s; direct TCP — long streams dying 2 in 3, once a silent
`ReadTimeout`, once a `RemoteProtocolError`, with a healthy run in between
proving the endpoint was fine). A third region would bet on the next path.
Colocation deletes the path instead of hardening it.

| Requirement | Value | Why |
|---|---|---|
| Architecture | **native x86_64 Linux** | SWE-bench images are x86_64; pass `--platform ''` so Docker does not emulate |
| GPU | **≥ 48 GB, 80 GB preferred** | `Qwen/Qwen3.6-27B-FP8` is 30.9 GB of weights; at 48 GB roughly 17 GB is left for KV cache and `max_model_len: 131072` may not fit |
| Docker | working, same host | SWE-bench containers run here |
| Disk | **≥ 100 GB free** | gate 2 fails below this |
| Python | 3.11+ with the repo's eval venv | `run_c2.py` imports `yaml`, `mini-swe-agent` |

**Not a bare A100 requirement.** Any card that fits the weights with KV headroom
will do; 80 GB is preferred only because it avoids the `max_model_len` fallback
below.

### The chosen host — GCE `a2-ultragpu-1g`

1 × A100 80 GB, 12 vCPU, 170 GB RAM. A full x86_64 VM running Docker natively,
and 80 GB very likely keeps the frozen `max_model_len: 131072`, which removes a
fallback and an explanation from the write-up.

```
machine type    a2-ultragpu-1g          GPU comes with the machine type; no --accelerator
provisioning    STANDARD, not Spot      a preemption mid-batch is a wasted A100 hour
image           ubuntu-2204-lts, x86_64
boot disk       >= 200 GB pd-ssd        results live here
local SSD       model cache only        does not survive a stop; never the only copy of a result
network         SSH only                vLLM binds localhost; no ingress rule for 8000
maintenance     TERMINATE, no restart   a maintenance event must fail the run visibly
```

`--maintenance-policy=TERMINATE` is mandatory for GPUs and is also what we want.
`--no-restart-on-failure` matters for the same reason: results from an
auto-restarted run must never be mixed into the original batch.

**Check quota before creating anything.** A new project ships
`NVIDIA_A100_80GB_GPUS = 0`, and raising it is a request with a turnaround — it
blocks harder than any step below. Need `A2_CPUS ≥ 12` and
`NVIDIA_A100_80GB_GPUS ≥ 1` in the chosen region, and a region that actually has
A2 Ultra capacity.

```sh
bash inference/gcp_provision.sh      # checks quota, then creates the VM
```

`inference/vm_setup.sh` runs on first boot: driver, Docker, NVIDIA Container
Toolkit, repo at the frozen commit `34ba1fc`. After it reports ready:

```sh
uname -m
nvidia-smi
docker run --rm hello-world
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

A driver installed at boot usually needs one reboot before `nvidia-smi` works.

**GCP avoids the corporate-VPN and proxy failures that killed the RunPod paths,
but that is not something to assume.** `curl google.com` proves nothing about
this experiment. The gate's checks 3–7 make real model requests, including an
8000-token completion and three 5000-token streams; that is what has to pass.

---

## 1. Get the data onto the host

The archives are gitignored (`.gitignore:17`, `data/runs/*/*.archive/`), so a
clone is **not** enough. C2 forks from archived states; without them every spec
fails closed.

```sh
git clone <repo> agentseism && cd agentseism
rsync -av --info=progress2 <mac>:~/project/agentseism/data/runs/ data/runs/
du -sh data/runs          # expect ~122 MB
```

---

## 2. Serve the model

```sh
vllm serve Qwen/Qwen3.6-27B-FP8 \
  --revision e89b16ebf1988b3d6befa7de50abc2d76f26eb09 \
  --max-model-len 131072 --gpu-memory-utilization 0.90 \
  --tensor-parallel-size 1 --enable-prefix-caching --max-num-seqs 4 \
  --port 8000
```

Parameters come from `inference/configs/model_h2.yaml`; do not improvise them.

**The one parameter to confirm at boot rather than assume.** `max_model_len`
reserves KV cache and vLLM refuses to start if the pool cannot hold one
full-length sequence. If it refuses, the registered fallback is **65536 with a
recorded note** — not a silent retry at a smaller value, because every
continuation in the experiment must be served at the same length. Record which
value actually served.

Record, do not configure: `vllm_version`, `torch_version`, `cuda_version`,
`driver_version`, `gpu_name`.

---

## 3. The gate — eight checks, before any C2 data

```sh
bash inference/vm_gate.sh 2>&1 | tee /tmp/c2_gate.log
```

1. the card — `nvidia-smi`
2. Docker on this host, and ≥ 100 GB free
3–6. the endpoint over localhost, including an 8000-token completion
7. the realistic worst case, three times — a 5000-token stream, since the
   largest single completion anywhere in the H2 data was 4954 tokens. This is
   the observed worst case, **not a bound**: the agent sets no `max_tokens`.
8. **replay equivalence** — replays `r4` to step 31 and requires every tracked
   state to reproduce exactly.

Gate 8 is the one that exists because of C2.2. The source trajectories were
recorded under x86 emulation on arm64 macOS; continuing them natively means the
prefix was observed under emulation and the continuation runs on real hardware.
If states do not reproduce, **that is a finding about emulation fidelity and
must be recorded as one.** There is no "run a few and see" — a host that does
not reproduce the recorded states makes every continuation diverge for an
infrastructure reason, which is indistinguishable from the effect C2 measures.

**Any gate failure ⇒ no C2 data is collected.** Keep `/tmp/c2_gate.log` and
`/tmp/c2_equivalence.log`; they are the provenance that the host reproduced the
recorded states.

---

## 4. Execute, in three modes, in order

```sh
export PYTHONPATH=.
python experiments/coding/run_c2.py --dry-run               # 72 specs, every archive resolved
python experiments/coding/run_c2.py --validate --platform ''  # rebuild one container per arm × horizon
```

### Then stop, and price the batch

**Do not start the full run until the budget is known.** An A100 80 GB bills for
every hour the instance exists, idle included, and 72 continuations of unknown
duration is not a number anyone should commit to blind.

Time exactly one continuation, then compute the ceiling:

```sh
time python experiments/coding/run_c2.py --platform '' --out data/runs/c2_timing
# stop it after the first spec completes
```

```
worst case hours  =  72 x (slowest observed continuation, hours)  +  setup +  download
worst case cost   =  worst case hours  x  (a2-ultragpu-1g hourly rate)
```

Use the **slowest** observed continuation, not the mean: the H2 data contains
single attempts that ran 1157 s, 3463 s and 3559 s. Record the figure alongside
the gate logs. If the ceiling is unacceptable, the decision is which arm to run
first — not which specs to drop, and not a threshold change.

### Only then, the full batch

```sh
python experiments/coding/run_c2.py --platform '' --out data/runs/c2
```

`--platform ''` because the host is native x86; the default is for the emulated
Mac.

**Fail closed is the point.** A fork whose archived source state, workspace
fingerprint or message prefix does not match what was recorded is not run with a
warning — it stops the spec, and `--validate` stops the batch. Do not work around
a mismatch. Investigate it.

Nothing about the plan is a command-line option. Horizons, trajectories and
replication counts come from `c2_protocol.py`, which is the registration turned
into data; a flag that could change them is a flag that eventually would.

Resume is by completion: a spec whose output already carries an `exit_status` is
skipped, so an interrupted batch is restarted with the same command.

---

## 5. Freeze before analysing

In this order, and each before the next exists:

1. `rsync` the raw outputs back, or commit them on the host.
2. Commit the raw artifacts **untouched**, with the gate log and the equivalence
   log alongside them.
3. Record the host: GPU, driver, vLLM/torch/CUDA versions, the `max_model_len`
   that actually served.
4. Verify integrity before computing anything: 72 specs present, each with an
   `exit_status`, no spec short of its replicates.
5. Only then run the analysis.
6. **Delete the instance.** Verify the raw results and their hashes are off the
   VM first — local SSD does not survive a stop, and an A100 bills while idle.

This is the same discipline Phase 2 used in the other project, and it is what
makes the chain *frozen configuration → raw results → analysis* auditable.

---

## 6. Analyse by the registered rule, and nothing else

The pre-registration fixes the quantity and the readout. Do not add an
exploratory readout to the same batch; if something else looks interesting,
record it as a candidate for a separate, separately registered experiment.

C2 answers one question:

> By the time failure becomes visible, is the run still recoverable?

with `steering window = predictable ∩ still recoverable`. C1 located the left
edge, late — separation reaches a medium effect only around h ≈ 24 and a large
one around h ≈ 28, three quarters through a median 32–33-step run. C2 measures
whether the window has any width.

---

## 7. What the result decides

C2 is not one more table. It decides what AgentSeism claims, per
`docs/DESIGN-ci-stochastic-regression.md` §13 Phase 0:

| C2 outcome | Product promise |
|---|---|
| **Recoverable after divergence** | CI locates the earliest actionable point; replay/repair is supportable. |
| **Recoverable only earlier** | The recoverable window becomes the headline metric, and guides checkpoint placement. |
| **Essentially unrecoverable** | Promise no repair. Move to regression detection, root-cause localisation and observability. |

Until C2 reports, the §9 planted-regression experiment stays unfrozen, and no
observability, benchmark or additional agent integration work starts. Those
would be built on an unsettled product claim.
