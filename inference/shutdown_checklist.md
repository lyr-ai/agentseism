# Shutdown checklist

Run through this every time, including the times the run failed early. The most
expensive GPU is the one left running after a session that did not work.

## Before terminating

- [ ] `runs/<timestamp>/` copied off the instance — `stack.txt`, `health.txt`,
      `stress.json`, `gpu.csv`, `qualification.json`, `agent.txt`
- [ ] `stack.txt` actually contains the vLLM, torch, CUDA and driver versions.
      Without it the run is not reproducible and the money bought nothing.
- [ ] Wall-clock and hourly rate written into the experiment log, so
      cost-per-run is a measured number rather than an estimate. The local
      lesson: an estimate read off wall time was wrong by five times.

## Terminating

- [ ] Compute instance **terminated**, not stopped — a stopped instance often
      still bills for attached storage, and on some providers for the reservation.
- [ ] Provider console reloaded and the instance confirmed gone.
- [ ] Persistent volume: keep it if the model weights are worth re-using, and
      know the monthly rate. A 60 GB volume is cheap next to re-downloading
      weights on every rental, and it is not free.
- [ ] Any public IP or load balancer released.
- [ ] Billing page checked once, after termination, and the actual charge
      recorded next to the estimate.

## If the session is abandoned midway

Terminate first, diagnose afterwards. Nothing on the instance is worth
diagnosing at an hourly rate that a copied log cannot answer offline.
