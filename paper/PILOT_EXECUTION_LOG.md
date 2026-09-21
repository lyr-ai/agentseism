# Pilot execution log

The pilot registered in `PREREG_PILOT.md` (frozen at `2ff84bb`). One record per
host, appended in order. A host that ran no pilot cell still gets a record:
the reason a host was abandoned is part of the cost account.

---

## preflight_host_1 — 2026-09-20/21

```text
status               = stopped_before_pilot
reason               = billing_baseline_unrecoverable
instance_started_at  = 2026-09-20T23:58:46Z
pilot_runs           = 0
model_requests       = 0
```

**Provisioned.** Lambda, 1× H100 80 GB PCIe, x86_64, us-west-3.

**Preflight checks — all pass.**

| check | reading |
|---|---|
| `uname -m` | `x86_64`, kernel 6.8.0-1046-nvidia, Ubuntu 22.04 |
| GPU | 1× H100 PCIe, 81559 MiB, 0 MiB in use, no processes |
| driver / CUDA | 580.105.08 / 13.0 |
| Docker | client+server 29.2.1, API 1.53, daemon active |
| disk | 968 GB free of 993 GB |
| RAM / vCPU | 221 GB / 26 |
| Python | 3.10.12 |
| NVIDIA Container Toolkit | 1.18.1 |

**One host preparation action.** `ubuntu` was absent from the `docker` group
(the group existed and was empty), so the socket refused a non-root client.
`sudo usermod -aG docker ubuntu`; after re-login `id` carries `998(docker)`,
`docker version` reports the server without `sudo`, and `docker run --rm
hello-world` exits 0. The runner was **not** changed to `sudo docker`. This
happened before any fingerprint was frozen and before pilot run 0, so it is
host preparation, not an experimental change.

**Why the host was abandoned.** The billing baseline must be the cumulative
account total *before* this instance launched, because the registration puts
launch, preparation, model download and teardown inside the pilot's cost. The
instance was already billing before the Usage page was read, and no pre-launch
cumulative total could be recovered from it. Freezing the current total as the
baseline would have deleted the launch-to-baseline interval from the pilot's
recorded cost.

The alternative — reconstructing the missing amount from boot time × hourly
price — was rejected. `budget.py` exists to keep an estimate from ever
authorising anything, and an estimate substituted for the origin is worse than
one substituted for a reading: every later difference inherits it.

So: 0 pilot runs, 0 model requests, no weights downloaded, no vLLM started, GPU
never left 0 MiB. The instance was terminated.

**Ordering for host 2**, which is the whole point of this record:

1. Terminate host 1 and wait for Lambda's Usage page to take up its charges.
2. Read the page with nothing running — cumulative total, currency, billing
   period, UTC time of the reading. Keep a screenshot.
3. Freeze that value as the **pre-launch baseline**.
4. Only then launch the replacement (same shape: 1× H100 80 GB PCIe).
5. Enter the current cumulative total as reading #1 immediately after launch.

Under that order `pilot_spend = current_total − baseline` contains the new
instance's billed increment and nothing else, and the launch interval is inside
it rather than lost before it.

**Gate for host 2.** The local suite must be green before the next boot. At the
time of writing it is not: 9 `test_c2h_backend.py` failures and one
uncollectable module, all `ModuleNotFoundError: minisweagent` — `.venv` has
`agentseism` without `minisweagent`, `.venv-eval` the reverse. That is an
environment defect, not a product failure, and it is fixed locally at no
instance cost. Two real defects found during this preflight were fixed and
committed separately: the registered `$20` warning was documented but inert
(`c1813be`), and the CLI regression test was seeded with `hash()`, hence
salted per process and failing about one run in eight (`1874833`).
