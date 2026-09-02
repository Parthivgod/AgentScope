# Evaluation Results

*Manuscript section — Track B draft (Week 11). Every quantitative claim below cites the CHANGELOG.md entry (date/title) and underlying artifact that produced it. Target values from the PRD are labeled as targets; measured values are labeled as measured. Nothing here asserts a PRD goal as an achieved result.*

**Environment for all measurements:** local docker-compose deployment (Redis 7, FastAPI backend ×4 workers, anomaly worker, Nginx), Windows 11 host, all traffic through the Nginx front door unless noted. AWS deployment is pending; no measurement below involves a cloud instance.

**Current-build checkpoint (2026-08-31):** the four correctness/performance fixes identified on 2026-08-30 were implemented and the production protocols were rerun before the AgentScope/Langfuse/Phoenix comparison. Full protocols, raw paired trials, bootstrap intervals, limitations, and reproduction context are in `evaluation-artifacts/2026-08-31-post-fix/RESULTS.md`. The 2026-08-30 directory is preserved as pre-fix evidence rather than reused as a current result.

## Latency (NFR 9.1 / FR-3: event-to-dashboard latency < 200ms p95 — *target*)

Event-to-dashboard latency — POST /ingest until the same span arrives on a dashboard WebSocket — was measured with a concurrent probe (`infra/loadtest/event_latency_probe.py`) while Locust generated mixed background load:

| Load | n | p50 | p95 | p99 | Source |
|---|---|---|---|---|---|
| Idle | 100 | 47ms | 63ms | 63ms | CHANGELOG [2026-08-21 23:50] Week 9 Track B |
| 10 users, 1 backend worker | 200 | 125ms | 219ms | 360ms | same |
| 10 users, 4 workers | 198 | 47ms | 63ms | — | same |
| 50 users, 4 workers | 300 | 78ms | **156ms** | 218ms | same |

**Older-build result:** the 2026-08-21 build measured 156ms p95 under 50-user concurrent load. The 2026-08-30 current-build rerun did not reproduce that result, so the target is not currently accepted as met. Before the older read-path optimization, the same 2026-08-21 scenario measured p50=1700ms / p95=3600ms.

Raw HTTP endpoint percentiles at 50-user saturation remain above 200ms (aggregate p95=320ms) — reported as measured; the NFR is defined on event-to-dashboard latency, which passes.

Current-build compose measurements through Nginx were:

| Current-build condition | n | p50 | p95 | p99 | Probe errors |
|---|---:|---:|---:|---:|---:|
| Idle, persisted DB 0 | 300 | 63.0ms | 78.0ms | 94.0ms | 0 |
| Idle, initially empty DB 14 | 300 | 62.0ms | 63.0ms | 78.0ms | 0 |
| 50 users, persisted DB 0 | 300 | 594.0ms | 1312.0ms | 1766.4ms | 0 |
| 50 users, initially empty DB 14 | 300 | 235.0ms | **1642.5ms** | 2516.2ms | 0 |

Both current full-stack load trials miss the <200ms p95 target. In the controlled empty-database run, Locust completed 4,371 requests at 69.50 requests/s with one failure and 1600ms aggregate p95. A diagnostic control that separated the backend read path from the worker/anomaly database improved probe p95 to 625.7ms and throughput to 132.50 requests/s, but still missed the target. The clean full-stack database accumulated 1,157 anomaly records during the test; combined with full anomaly-stream scanning on history reads, this identifies a likely major bottleneck, not a complete causal proof.

After trace-isolated/lifecycle-deduplicated Failure Loops state and indexed anomaly history lookup, the final exact-code production run measured idle p50/p95/p99 of 47.0/63.0/78.0ms and concurrent 50-user p50/p95/p99 of 47.0/**78.0**/109.0ms (n=300 each, zero probe errors). Locust completed 13,675 requests with zero failures at 228.09 requests/s. Relative to the pre-fix clean full-stack run, throughput increased 3.28× and probe p95 fell 95.3%; because the trials were sequential, this is an associated before/after improvement rather than a component-level causal estimate. The <200ms event-to-dashboard target is met in this local condition, while aggregate HTTP p95 remains 610ms; independent repetitions and a longer stationarity probe are still required for a broad production claim.

## SDK overhead (NFR 9.5: <5% — *target*)

Measured on the branching demo-agent workload, 30 paired interleaved runs, no outlier removal (CHANGELOG [2026-08-21 23:30] Week 9 Track A; raw logs `sdk/agentscope/benchmarks/results/`):

- **Demo workload as-is** (CPU-trivial, ~4.7ms/graph): +3.3ms mean absolute overhead, **+79.7% mean / +60.7% median relative** — the <5% target is not applicable at this workload scale; any instrumentation dominates a sub-10ms graph.
- **LLM-bound workload** (100ms simulated LLM latency per node, ~208ms/graph): +3.6ms mean absolute, **+1.76% mean and median relative** — target met on the workload class it was written for.

The final 2026-08-31 matched run used 30 measured pairs after five warm-ups and verified 70 newly ingested AgentScope traces. CPU-trivial overhead was +2.057ms / +84.19% mean (bootstrap 95% interval 58.75–117.07%); LLM-bound overhead was +8.443ms / +4.04% mean (2.64–5.50%). Because the LLM-bound interval crosses 5%, the final run does not support an unqualified “target met” claim. The timed region excludes asynchronous delivery flush by design; completed ingestion was verified after flush.

## Delegation-context fidelity and privacy-preserving comparison

On the current checkout, all 107 framework-free delegation scenarios passed exact parent, owner, chain, hop, and trace checks, including 100 concurrent chains; exception and cancellation restoration also passed. In a balanced 200-case loop ablation, full capture and HMAC redaction both achieved 100/100 TP and 100/100 TN, while literal-only redaction produced 100/100 false positives on changing protected values. A sentinel scan found no raw protected input/output in the wire object. These are deterministic mechanism-level results; external validity still requires additional real workloads.

## Comparative evaluation vs. Langfuse and Arize Phoenix (RQ8)

The final matched local comparison used the same deterministic graph, Python and LangGraph versions, full capture policy, 30 measured trials per workload/product after five warm-ups, no outlier removal, and verified 70 newly ingested traces in every product. AgentScope and Langfuse used seeded AB/BA pairing; Phoenix required a baseline phase before process-global instrumentation. The older n=15 Phoenix-only result is superseded as the final-build comparison.

| Workload | AgentScope mean overhead (95% bootstrap CI) | Langfuse | Phoenix |
|---|---:|---:|---:|
| CPU-trivial | **84.19%** (58.75–117.07) | 185.56% (160.72–211.28) | 174.32% (150.91–197.88) |
| LLM-bound (100ms/node) | **4.04%** (2.64–5.50) | 4.31% (3.84–4.80) | 5.48% (4.64–6.34) |

AgentScope had the smallest point estimate in both workloads. Its LLM-bound interval overlaps Langfuse's, so this run does not establish a reliable difference between those two products. The quantitative scope is overhead and verified ingestion only; it does not rank diagnostic feature breadth, UI, resource use, setup effort, or query latency, and it does not pretend that a custom AgentScope detector is built into either baseline.

## Resilience (Test #6, NFR 9.2)

All from CHANGELOG [2026-08-22 00:45] (Track A) and [2026-08-22 01:20] (Track B):

- **Backend killed mid-run:** monitored agent completed 30/30 workloads with correct outputs, exit 0, no exceptions — only fail-silent sender warnings.
- **Worker killed mid-ingestion:** ingestion unaffected, zero lost events; worker caught up from its checkpoint after restart.
- **Redis full restart:** zero accepted events lost (AOF persistence); ingestion self-recovered within ~2s.
- **Stalled WebSocket consumer:** ingest p50/p95 unchanged (48/52ms vs. 48/52ms baseline).

## Security (Test #7, NFR 9.3)

CHANGELOG [2026-08-21 23:50] and [2026-08-22 01:20]: unauthenticated and invalid-key ingestion rejected with 401 through Nginx on both plain and TLS listeners, including under load (all 1272 unauthenticated requests correctly 401 during the 50-user load test). TLS 1.3 termination verified locally with a self-signed certificate (the reference deployment substitutes a real certificate); the WebSocket relay works over TLS. Redaction (NFR 9.4) verified at the wire level: with redaction enabled, raw payload strings are absent from every byte leaving the SDK process (CHANGELOG [2026-08-22 00:45]).

## Anomaly detection precision/recall (PRD targets: ≥90% precision / ≥85% recall)

The 2026-08-31 post-fix runner reevaluated the unchanged 1,200 labeled scenarios with separate 600-case tuning and 600-case held-out splits. On each rule's 100 held-out cases, all six production rules measured precision=recall=F1=1.000 (50 TP, 50 TN, 0 FP, 0 FN; Wilson 95% interval 0.929–1.000 for precision and recall). Failure Loops improved from the pre-fix 0.714 precision/0.833 F1 after state was keyed by `(trace_id, agent_id)` and duplicate lifecycle versions were collapsed by `span_id`. The declared precision and recall targets are met on this corpus; these remain synthetic-corpus measurements, not field prevalence estimates or evidence of perfect generalization.

## Live/historical convergence

After atomic event/index writes and authoritative Redis stream-ID sorting, the production-compose test matched event multiset, exact arrival order, and dashboard-equivalent latest state in all 9/9 continuously connected burst runs. The reconnect-gap run also received all 20 expected lifecycle events in exact order and converged with history by resuming after the last durable event/anomaly cursors. This bounded result assumes the referenced stream entries remain retained; stream trimming, invalid cursors, and Redis loss require separate policies and tests.

## Dashboard accessibility

CHANGELOG [2026-08-21 00:20] Week 9 Track C and [2026-08-22 01:40] Week 10 Track C: axe-core 0 violations (from 1 serious violation pre-fix); Lighthouse accessibility 100; graph nodes keyboard-accessible with status glyphs and dashed anomalous borders providing non-hue state distinction for colorblind users. Performance Lighthouse score (39) was measured on the dev server and is not representative of a production build — no performance claim is drawn from it.

## Usability (Test #9)

Requires a live session with an unfamiliar human observer; the test scenario and injection tooling are prepared, but the session has not been conducted. **No usability findings are reported** — the section will be written only after the real session (see the Week 11 Track C changelog entry and `docs/usability-test-prep.md`).
