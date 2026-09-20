## AgentSeism: INCOMPARABLE — these runs cannot be compared

Rebuild the baseline on this stack, or explicitly approve the comparison. No regression was computed.

**Fingerprint fields that differ**

- `serving_runtime`

Trials run: **0** — the check stops before spending on a comparison that cannot be used.

**Evidence**

- Same model id, revision, vLLM, CUDA, weights, prompt and scaffold. **The agent did not change.**
- Only the serving path moved: A100-SXM4-80GB → H100 PCIe, driver 580.126.16 → 580.105.08.
- Structured actions differ on **23 of 23** fork roots.
- Without this gate that difference would be reported as an agent regression on every root.
- Source: `data/runs/gate9`, recomputed from frozen artifacts.

---

<sub>contract `default-1` `1e3047d6fefbdae6` · protocol v1</sub>
