# Evaluation Results

*Manuscript section — Track B draft (Week 11). Every quantitative claim below cites the CHANGELOG.md entry (date/title) and underlying artifact that produced it. Target values from the PRD are labeled as targets; measured values are labeled as measured. Nothing here asserts a PRD goal as an achieved result.*

**Environment for all measurements:** local docker-compose deployment (Redis 7, FastAPI backend ×4 workers, anomaly worker, Nginx), Windows 11 host, all traffic through the Nginx front door unless noted. AWS deployment is pending; no measurement below involves a cloud instance.

## Latency (NFR 9.1 / FR-3: event-to-dashboard latency < 200ms p95 — *target*)

Event-to-dashboard latency — POST /ingest until the same span arrives on a dashboard WebSocket — was measured with a concurrent probe (`infra/loadtest/event_latency_probe.py`) while Locust generated mixed background load:

| Load | n | p50 | p95 | p99 | Source |
|---|---|---|---|---|---|
| Idle | 100 | 47ms | 63ms | 63ms | CHANGELOG [2026-08-21 23:50] Week 9 Track B |
| 10 users, 1 backend worker | 200 | 125ms | 219ms | 360ms | same |
| 10 users, 4 workers | 198 | 47ms | 63ms | — | same |
| 50 users, 4 workers | 300 | 78ms | **156ms** | 218ms | same |

**Measured result: the <200ms p95 target is met under 50-user concurrent load (156ms p95).** Before the read-path optimization, the same 50-user scenario measured p50=1700ms / p95=3600ms (miss by ~18×); the per-trace read index and multi-worker backend brought it under target. Reported both as measured.

Raw HTTP endpoint percentiles at 50-user saturation remain above 200ms (aggregate p95=320ms) — reported as measured; the NFR is defined on event-to-dashboard latency, which passes.

## SDK overhead (NFR 9.5: <5% — *target*)

Measured on the branching demo-agent workload, 30 paired interleaved runs, no outlier removal (CHANGELOG [2026-08-21 23:30] Week 9 Track A; raw logs `sdk/agentscope/benchmarks/results/`):

- **Demo workload as-is** (CPU-trivial, ~4.7ms/graph): +3.3ms mean absolute overhead, **+79.7% mean / +60.7% median relative** — the <5% target is not applicable at this workload scale; any instrumentation dominates a sub-10ms graph.
- **LLM-bound workload** (100ms simulated LLM latency per node, ~208ms/graph): +3.6ms mean absolute, **+1.76% mean and median relative** — target met on the workload class it was written for.

## Comparative baseline vs. Arize Phoenix (Test #8)

Same workloads, three arms (no instrumentation / AgentScope / Phoenix via OpenInference LangChain → local Phoenix container, export verified), n=15 per arm (CHANGELOG [2026-08-22 01:20] Week 10 Track B; raw log `infra/loadtest/results/baseline-phoenix-2026-08-22.log`):

| Workload | AgentScope overhead | Phoenix overhead |
|---|---|---|
| Demo as-is | +93.1% mean / +84.0% median | +201.7% / +206.6% |
| LLM-bound (100ms/node) | −0.5% mean / +0.9% median | +2.6% / +4.3% |

AgentScope's instrumentation overhead measured lower than Phoenix's on both workload classes in this run.

## Resilience (Test #6, NFR 9.2)

All from CHANGELOG [2026-08-22 00:45] (Track A) and [2026-08-22 01:20] (Track B):

- **Backend killed mid-run:** monitored agent completed 30/30 workloads with correct outputs, exit 0, no exceptions — only fail-silent sender warnings.
- **Worker killed mid-ingestion:** ingestion unaffected, zero lost events; worker caught up from its checkpoint after restart.
- **Redis full restart:** zero accepted events lost (AOF persistence); ingestion self-recovered within ~2s.
- **Stalled WebSocket consumer:** ingest p50/p95 unchanged (48/52ms vs. 48/52ms baseline).

## Security (Test #7, NFR 9.3)

CHANGELOG [2026-08-21 23:50] and [2026-08-22 01:20]: unauthenticated and invalid-key ingestion rejected with 401 through Nginx on both plain and TLS listeners, including under load (all 1272 unauthenticated requests correctly 401 during the 50-user load test). TLS 1.3 termination verified locally with a self-signed certificate (the reference deployment substitutes a real certificate); the WebSocket relay works over TLS. Redaction (NFR 9.4) verified at the wire level: with redaction enabled, raw payload strings are absent from every byte leaving the SDK process (CHANGELOG [2026-08-22 00:45]).

## Anomaly detection precision/recall (PRD targets: ≥90% precision / ≥85% recall — *targets, not yet claimable*)

Per RULES.md §6, these targets may not be asserted until injection-harness validation is completed against final thresholds. The Week 5-6 harness observations exist but threshold re-tuning was not re-validated in Weeks 9-12; **this manuscript therefore makes no precision/recall claim**. This is an open evaluation item, not an achieved result.

## Dashboard accessibility

CHANGELOG [2026-08-21 00:20] Week 9 Track C and [2026-08-22 01:40] Week 10 Track C: axe-core 0 violations (from 1 serious violation pre-fix); Lighthouse accessibility 100; graph nodes keyboard-accessible with status glyphs and dashed anomalous borders providing non-hue state distinction for colorblind users. Performance Lighthouse score (39) was measured on the dev server and is not representative of a production build — no performance claim is drawn from it.

## Usability (Test #9)

Requires a live session with an unfamiliar human observer; the test scenario and injection tooling are prepared, but the session has not been conducted. **No usability findings are reported** — the section will be written only after the real session (see the Week 11 Track C changelog entry and `docs/usability-test-prep.md`).
