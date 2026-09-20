# C2-H — pre-rental audit and deployment checklist

**Date:** 2026-09-20 · **Audited at:** `b764a29` + this commit
**Verdict:** **CONDITIONAL GO** — see §10.

No machine rented, no model called, no container run during this audit. An
autouse test fixture fails any test that invokes Docker.

---

## 1. Diff since the pre-registration `939f118`

Six commits. Classified, because "we changed the protocol" and "we implemented
it" must not be told apart by reading a diff later.

| Commit | Class | What |
|---|---|---|
| `78e7184` | **implementation** | `c2h_protocol.py` materialises the registered values; budget state machine; `--resolve-only` |
| `2a10b32` | **implementation** | execution path, manifest freezing, block loop, four terminal states |
| `f397ff1` | **implementation** | real backend, inert construction, mock-tested |
| `813bf97` | **terminology** | `donor_seed` → `acquisition_index`. No registered value moved; `protocol_hash` unchanged at the time |
| `0e78971` | **implementation** | frozen checker bound, verified 20/20 offline; retry guards |
| `b764a29` | **substantive (registered)** | `TASK` and `IMAGE` added to the registration and to `protocol_hash` |

**One substantive change**, and it is an addition rather than a revision: the
task and image were always implied by the feasibility analysis and are now
registered explicitly, which moved the hash. It predates any donor and any
frozen manifest, and is recorded in prereg §4b.

**No registered value was altered.** Horizons, arm sizes, replicate counts,
donor cap, concurrency, subset definition, budget thresholds and checkpoints
are exactly as §3–§6 registered them.

- [x] Every registered value in `c2h_protocol.py` matches the prereg text.

## 2. Protocol hash consistency

```
current   1fda86fedc297132
previous  30e43200e97e148b   (before TASK/IMAGE were registered)
```

- [x] `1fda86fedc297132` is the value the runner computes.
- [x] It enters the **session fingerprint** and is drift-checked, so a run
      cannot continue under a changed registration.
- [x] It is written into every `session` log record and every `manifest_frozen`
      record.
- [x] The old hash appears only in prereg §4a/§4b as history, and §4a now says
      explicitly that the current value is `1fda86fedc297132`.
- [x] No code accepts the old hash.

## 3. Deterministic reconstruction

`--resolve-only`, run twice, byte-identical:

```
protocol 1fda86fedc297132   manifest 9631c1708936da73   order f398cf46bfba1a9d
```

- [x] 72 specs — full cartesian product, every cell distinct.
- [x] 36 descriptive subset — strict, nested, by replicate index only; drops no
      donor, horizon or arm.
- [x] 24 blocks — partition the specs, FAIL before PASS, sizes 4 / 2.
- [x] Order hash deterministic across runs.
- [x] Manifest hash above is for **placeholder** donors; the real one is fixed
      when §4 binds donors, and is logged then.

## 4. Image digest, resolved before donor 0

Lazy resolution was a defect and is fixed: the digest used to appear only when
the first container was built, so the session was bound with
`image_digest: None` and a moved tag would have surfaced mid-experiment.

- [x] `preflight()` runs before the first donor and resolves the digest.
- [x] It verifies the tag is the registered one; otherwise `registered_target`.
- [x] A digest that cannot be resolved is `image_digest` — a stop, not a warning.
- [x] `_execute` refuses outright if `preflight()` has not run.

## 5. Session fingerprint

Thirteen fields, all drift-checked, and the comparison walks **every recorded
key** rather than a hard-coded list, so a new field cannot escape it:

```
hostname  boot_id  machine  gpu  vllm_pid  endpoint  model_id  revision
task  image  image_digest  dependency_lock_sha256  protocol_hash
```

- [x] A restarted vLLM is a different session **by design**, and stays refused.
- [x] `dependency_lock_sha256` binds `requirements-vllm.lock.txt`.

## 6. Gates on the real backend

- [x] `--backend` defaults to `fake`.
- [x] `--backend real` without `--execute-registered-c2h` refuses.
- [x] `--image` is not a CLI option; the target is registered.
- [x] `--resolve-only` never constructs the backend, even with `real` selected.

## 7. Transport

- [x] Registered policy used verbatim: `stream=True`, `attempt_timeout=180`,
      `max_attempts=6`.
- [x] `num_retries == 0` underneath is **checked**, at construction and in
      `preflight`; anything else is `transport_policy`.
- [x] Behavioural test: one logical request enters the transport exactly once.
- [x] Every record carries `transport_attempts`; an absent count is a stop.
- [x] The grep guard remains, as a supplement rather than the evidence.

## 8. Budget, donors and integrity

- [x] **Thresholds apply to this run's spend, not the account total.** A
      baseline is frozen before donor 0 and the state machine judges
      `current_total − billing_baseline`. The account already carries the first
      H100's Gate 9 spend; comparing the raw page total against `$85` would have
      charged C2-H for money spent before it existed. **This was the last
      blocking defect and is fixed.**
- [x] A reading below the baseline, a changed billing period or a changed
      currency each stop rather than being differenced.
- [x] The operator enters page totals only; `record_reading` has no `delta` or
      `spent` parameter, and every record keeps baseline, total and delta.
- [x] `after_setup` runs **before donor 0** and requires a manual reading.
- [x] An estimate authorises nothing, at any checkpoint.
- [x] One reading authorises one block; reuse is `stale_reading`.
- [x] `$85` no new block · `$90` stop the stage · `$100` absolute.
- [x] Checker reproduces **20 / 20** frozen labels offline; 4 FAIL / 16 PASS.
- [x] Infra failure, missing report, unapplied patch, absent `resolved` →
      `invalid`: counted towards the cap, towards neither arm, never by hand.
- [x] Cap 30, earliest qualifying, manifest immutable once frozen.
- [x] Interruption, container failure, agent exception, artifact-digest
      mismatch → **no recoverability verdict**; `complete_72` alone permits one.
- [x] Artifacts written temp → fsync → rename, each with a `.sha256`; a failed
      write leaves the previous artifact standing.

## 9. Secrets and retrieval

- [x] No API key, token or personal path is written into any artifact; the only
      key reference is `OPENAI_API_KEY="not-needed"` for the localhost endpoint.
- [x] Scenarios are synthetic; the task is public SWE-bench.
- [ ] **Retrieval rehearsal** — see §10.

Emergency freeze and retrieve, to be pasted before starting anything:

```sh
# on the VM
cd ~/agentseism && tar czf /tmp/c2h.tgz data/runs/c2h
# from the laptop
scp ubuntu@<ip>:/tmp/c2h.tgz . && tar tzf c2h.tgz | head
```

---

## 10. Verdict — **CONDITIONAL GO**

Nothing is blocking that can be settled off a machine. Everything below can
only be confirmed **on the new instance, before the first donor**, and each is a
stop if it fails.

| # | Check, on the instance, before donor 0 |
|---|---|
| 1 | `docker image inspect` resolves a digest for the registered tag; record it |
| 2 | The digest matches the one used for the donors — **for C2-H this is the first use, so the digest is established here and frozen** |
| 3 | `nvidia-smi` GPU UUID, `boot_id`, hostname recorded |
| 4 | vLLM launched from `inference/configs/model_h2.yaml` via `start_vllm.sh`; the printed argv carries `--enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 --max-model-len 131072` |
| 5 | KV cache allocates at `131072`; **any fallback is a stop, not a downgrade** |
| 6 | `pip freeze` on the instance matches `requirements-vllm.lock.txt` |
| 7 | vLLM PID recorded; it must not change for the rest of the run |
| 8 | ≥ 100 GB free disk; model cached; image pulled |
| 9 | **Billing baseline frozen**: the page's cumulative total, its billing period and currency, entered manually. This is the origin; donor 0 cannot start without it, and it is never re-entered — a resume reuses it |
| 10 | Retrieval rehearsed once on an empty `data/runs/c2h` before real data exists |
| 11 | `--resolve-only` re-run on the instance; `protocol 1fda86fedc297132`, `order f398cf46bfba1a9d` |

Only after all eleven: `--backend real --execute-registered-c2h`.

**Not GO**, because items 1–3 and 9 are unobservable off the instance and the
run must not start without them. **Not NO-GO**, because no defect remains that
can be fixed from here — the three found in this audit (lazy digest, a
fingerprint missing four fields, a stale hash line in §4a) are fixed in this
commit.
