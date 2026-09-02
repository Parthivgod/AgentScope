# 2026-08-31 Post-Fix Evaluation and Three-Way Comparison

## Scope and environment

This run evaluates the current dirty checkout at commit `8add3385c693a165f705352df222e1cdbba78aea` after four production-path fixes: trace-isolated/lifecycle-deduplicated Failure Loops state, indexed anomaly retrieval, atomic ingest/index ordering with authoritative Redis stream-ID sorting, and cursor-based WebSocket reconnect catch-up. The local production path used Redis 7, four FastAPI worker processes, the anomaly worker, and Nginx on Docker Engine 29.3.1. Redis DB 12 was verified empty before the post-fix protocol; normal DB 0 and earlier DB 14 evidence were not deleted.

All reported comparison arms used Python 3.11.4, `langgraph==1.2.11`, `langchain-core==1.6.0`, 30 measured trials per workload after five discarded warm-ups, the same deterministic router-plus-specialist graph, full input/output capture, and no outlier removal. Raw paired observations are retained in each comparison JSON.

## Correctness outcomes

### Failure Loops isolation and lifecycle deduplication

The unchanged 1,200-scenario deterministic anomaly corpus has 600 tuning and 600 untouched held-out scenarios. Each rule has 50 positive and 50 negative held-out cases. Production parameters achieved:

| Rule | TP | TN | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Crashes | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| Failure Loops | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| Timeouts | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| Token Spikes | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| Message Storms | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| Delegation Cycles | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |

Failure Loops improved from 0.714 precision and 0.833 F1 in the pre-fix run to 1.000/1.000 because events are now isolated by `(trace_id, agent_id)` and duplicate active/completed versions of one `span_id` count once. The Wilson 95% interval retained in the raw artifact is 0.929–1.000 for both precision and recall; the perfect point estimate must not be generalized beyond this synthetic corpus.

### Ordering and reconnect convergence

Across nine continuous production-compose burst runs (10, 50, and 100 spans; three repetitions each), the live WebSocket and `/history` had identical event multisets, exact Redis arrival order, and identical dashboard-equivalent latest span state in 9/9 runs. The reconnect-gap case also received all 20 expected events in exact order and reproduced the same latest state as history after reconnecting from the last durable stream cursor. No event was missing or duplicated in these scenarios.

This closes the pre-fix observations of exact order in only 1/9 continuous runs and ten missed completion events during reconnect. The result covers bounded reconnect while retained Redis stream entries still exist; it is not a guarantee across stream trimming, Redis loss, or an invalid/expired cursor.

### Indexed anomaly history path

New backend tests prove that a ready per-trace anomaly index serves history without scanning the global anomaly stream, while a one-time migration preserves legacy records. Ingest now performs event stream append, trace registration, and per-trace stream-ID indexing in one Redis Lua operation. History sorts indexed IDs by parsed Redis stream ID, providing an authoritative order even for legacy/raced index entries. The current implementation retains a legacy full-scan fallback only until the anomaly-index readiness marker exists.

## Production performance after the fixes

| Condition | Samples | p50 | p95 | p99 | Errors |
|---|---:|---:|---:|---:|---:|
| Idle event-to-WebSocket | 300 | 47.0 ms | 63.0 ms | 78.0 ms | 0 |
| Concurrent 50-user event-to-WebSocket | 300 | 47.0 ms | **78.0 ms** | 109.0 ms | 0 |

During the final exact-code 50-user probe, Locust completed 13,675 requests with zero failures at 228.09 requests/s. Aggregate HTTP mean was 163.46 ms, p95 610 ms, p99 1,300 ms, and maximum 4,234.5 ms. Relative to the pre-fix clean full-stack run (69.50 requests/s and 1,642.5 ms concurrent event-to-WebSocket p95), throughput increased 3.28x and probe p95 fell 95.3%. These before/after trials were sequential rather than randomized, so they demonstrate a large associated improvement, not a component-level causal decomposition.

The declared event-to-dashboard target is met in this local 50-user condition because measured p95 is 78.0 ms, below 200 ms. The HTTP aggregate p95 remains 610 ms, and only one final exact-code run was collected; independent repetitions and a longer stationarity probe are required before making a broad production-performance claim.

The worker-kill recovery check accepted 70 spans while the worker was stopped midstream, observed the event stream advance while it was down, and observed the restarted worker advance its checkpoint to the final stream ID. This supports catch-up for that bounded run, not a universal no-loss claim.

## AgentScope / Langfuse / Phoenix matched comparison

Each arm ran in a fresh Python process. AgentScope and Langfuse used seeded AB/BA order within each baseline/instrumented pair. Phoenix instrumentation is process-global, so all Phoenix baselines had to run before its instrumented phase; this known order limitation is recorded in the raw artifact. The timed region is graph `ainvoke`; asynchronous exporter flush is excluded and performed before ingestion verification.

| Workload and arm | Baseline mean | Instrumented mean | Mean absolute delta (bootstrap 95% CI) | Mean overhead (bootstrap 95% CI) | Median overhead | Verified new traces |
|---|---:|---:|---:|---:|---:|---:|
| CPU-trivial — AgentScope | 2.697 ms | 4.754 ms | +2.057 ms (1.305–3.138) | **84.19%** (58.75–117.07) | 62.95% | 70 |
| CPU-trivial — Langfuse | 2.464 ms | 6.831 ms | +4.367 ms (3.898–4.863) | 185.56% (160.72–211.28) | 168.11% | 70 |
| CPU-trivial — Phoenix | 5.319 ms | 14.161 ms | +8.843 ms (7.787–10.089) | 174.32% (150.91–197.88) | 161.06% | 70 |
| 100 ms/node — AgentScope | 210.649 ms | 219.092 ms | +8.443 ms (5.480–11.497) | **4.04%** (2.64–5.50) | 3.02% | 70 |
| 100 ms/node — Langfuse | 206.936 ms | 215.852 ms | +8.916 ms (7.950–9.920) | 4.31% (3.84–4.80) | 4.49% | 70 |
| 100 ms/node — Phoenix | 208.998 ms | 220.460 ms | +11.462 ms (9.696–13.279) | 5.48% (4.64–6.34) | 5.28% | 70 |

AgentScope has the smallest mean absolute and relative overhead point estimate in both evaluated workload classes. On the 100 ms/node workload, however, AgentScope's 4.04% interval overlaps Langfuse's 4.31% interval; this run does not establish a statistically reliable AgentScope-versus-Langfuse difference. AgentScope's interval also extends above the project's 5% target, so the target is not accepted unconditionally despite the point estimate.

The CPU-trivial percentages are deliberately reported but are not representative of LLM-dominated agents: a 2–9 ms absolute instrumentation cost becomes a large percentage of a 2–5 ms baseline.

### Evaluated versions

- AgentScope: current checkout at commit `8add3385c693a165f705352df222e1cdbba78aea`.
- Langfuse SDK: 4.15.1. The server was launched from the official `v4.25.0` source tag (`60dfa8bc18ad3a71d26dec512d1c580de5ff2420`) with the official Compose stack; web image ID `sha256:12654de5ffb20722cf6b2d7df51b3099eb2d92bd92f5aef20e095b16a840ca8d`, worker image ID `sha256:638a46341ead4f68103f2b800a14b5d75f7c352b975f2b63a43697c577233a4c`.
- Phoenix server: `arizephoenix/phoenix:version-20.4.0`, image ID `sha256:8af594ab0342cc32acc4167f472fb89b4e25f5eb8d5e26c353bf4e102fddb693`; OpenInference LangChain instrumentation 0.1.73 and OpenTelemetry SDK/exporter 1.44.0.

### Comparison boundary

The quantitative comparison covers matched execution overhead and verified trace ingestion. It does not score diagnostic feature breadth, UI quality, resource consumption, setup time, query latency, or time-to-visible evidence. No synthetic detector was assigned to Langfuse or Phoenix, and no claim is made that they lack comparable capabilities outside the evaluated configuration. Their evaluations, dashboards, and OpenTelemetry/OpenInference support remain unmatched platform features for a later qualitative matrix and user study.

## Verification

- Worker focused regressions: 4 passed.
- Backend regressions: 16 passed.
- SDK regressions: 30 passed.
- Dashboard TypeScript/Vite production build passed; oxlint passed.
- Post-fix anomaly corpus: 1,200 scenarios completed.
- Production convergence: 9 continuous bursts plus one reconnect-gap scenario completed.
- Comparison: 30 measured trials × 2 workloads × 3 products, plus five warm-ups per product/workload; all arms verified 70 new traces.

## Artifact map

- `anomaly_validation_postfix.json`: complete tuning/held-out detector results and scenario-level outcomes.
- `live_history_convergence_postfix.json`: continuous and reconnect live/history comparisons.
- `latency_idle_postfix.json`, `latency_50u_postfix.json`: raw event-to-WebSocket samples.
- `locust_50u_postfix_*`: full 50-user HTTP load outputs and HTML report.
- `comparison_agentscope.json`, `comparison_langfuse.json`, `comparison_phoenix.json`: raw paired timing observations, bootstrap intervals, environment manifests, versions, and ingestion counts.
