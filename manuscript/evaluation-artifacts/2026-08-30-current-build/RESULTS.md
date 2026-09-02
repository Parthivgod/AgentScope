# Current-build evaluation: stages 1–4

Run date: 2026-08-30. Scope was deliberately limited to the first four items in the recommended sequence. The AgentScope/Langfuse/Phoenix three-way comparison was **not run**.

## Evidence boundary

Stages 1 and 2 are deterministic, current-checkout offline evaluations. Stage 3 includes a paired SDK benchmark against the live compose ingestion endpoint and latency/load trials through Nginx. Stage 4 uses the production Redis/FastAPI/Nginx path. Docker Desktop was unavailable at the beginning of the session, so preliminary `*_fallback` diagnostics were retained, but Docker was later started and the full protocols completed. Production conclusions below use the compose artifacts, not the fallback artifacts.

The first compose load run used persisted Redis DB 0. To separate prior data from current-run effects, the complete idle/load protocol was repeated with an initially empty DB 14. A diagnostic read-path control used an initially empty DB 13 for the backend while the worker continued on DB 14. That control is evidence about a bottleneck, not a production configuration.

## Stage 1 — Delegation fidelity and privacy ablation

The framework-free adapter was exercised through ordinary sync and async Python callables decorated with `@trace`; no multi-agent framework was present. All 107 evaluated chains passed exact parent-edge, agent-owner, delegation-chain, hop-number, and single-trace checks. This included depths 1, 2, 5, and 10; async depths 2, 5, and 10; and 100 concurrent depth-3 chains. No cross-task context leak was observed, and context was restored after both an exception and task cancellation.

The privacy ablation contained 200 balanced cases: 100 truly repeated protected inputs and 100 changing protected inputs, each evaluated in full-capture, literal-redaction, and HMAC-redaction modes.

| Mode | TP | FP | FN | TN | Accuracy | Agreement with full capture |
|---|---:|---:|---:|---:|---:|---:|
| Full capture | 100 | 0 | 0 | 100 | 1.000 | 1.000 |
| Literal `[REDACTED]` only | 100 | 100 | 0 | 0 | 0.500 | 0.500 |
| HMAC + redaction | 100 | 0 | 0 | 100 | 1.000 | 1.000 |

The wire-object sentinel scan found neither protected input nor protected output content and did find a 32-hex-character fingerprint. A simulated process-key rotation changed the fingerprint for the same value, confirming the intended process-lifetime comparison scope. Median redaction-preparation cost was 7.6 µs at 128 B, 25.8 µs at 4 KiB, 285.9 µs at 64 KiB, and 5.412 ms at 1 MiB. These are microbenchmarks of `_prepare_span_for_send`, not end-to-end latency.

Evidence: `novelty_evaluation.json`.

## Stage 2 — Labeled anomaly corpus

The runner generated 1,200 scenarios: 600 tuning and 600 untouched held-out scenarios, balanced per rule at 50 positive and 50 negative examples per split. Candidate thresholds were selected on the tuning split; production and tuning-selected settings were then evaluated on held-out data. Wilson 95% intervals are stored in the JSON artifact.

| Rule | Precision | Recall | F1 | FP | FN | Main observation |
|---|---:|---:|---:|---:|---:|---|
| Crashes | 1.000 | 1.000 | 1.000 | 0 | 0 | All held-out cases classified correctly |
| Failure loops | 0.714 | 1.000 | 0.833 | 20 | 0 | 10 cross-trace and 10 duplicate-version false positives |
| Timeouts | 1.000 | 1.000 | 1.000 | 0 | 0 | All held-out cases classified correctly |
| Token spikes | 1.000 | 1.000 | 1.000 | 0 | 0 | Single-call and session-rate cases passed |
| Message storms | 1.000 | 1.000 | 1.000 | 0 | 0 | Boundary and spread negatives passed |
| Delegation cycles | 1.000 | 1.000 | 1.000 | 0 | 0 | A→B→A positives and A→B→C negatives passed |

For each true positive, first detection occurred at the expected trigger event. Threshold search retained the production thresholds; it could not remove the Failure Loops false positives. `FailureLoopRule.history` is keyed only by `agent_id`, so identical calls from separate traces can merge, and active/completed versions of the same span are counted as separate calls. This is a state-keying and lifecycle-deduplication defect rather than a threshold-selection problem. The current corpus therefore does **not** support the manuscript's ≥90% precision target for Failure Loops. External/workload validation is still required before generalizing the other five synthetic results.

Evidence: `anomaly_validation.json`.

## Stage 3 — Current-build overhead and production performance

The live-ingest overhead runner used 30 paired runs per configuration, five discarded warm-up pairs, AB/BA counterbalancing, no outlier removal, 10,000-sample bootstrap intervals, `http://localhost/ingest`, and a drained sender queue.

| Workload | Baseline mean | Instrumented mean | Paired difference mean (bootstrap 95%) | Relative mean (bootstrap 95%) |
|---|---:|---:|---:|---:|
| CPU-trivial graph | 2.535 ms | 3.917 ms | +1.382 ms (1.115–1.693) | +70.18% (53.44–88.60) |
| 100 ms simulated delay per node | 210.498 ms | 218.964 ms | +8.467 ms (5.005–14.101) | +4.04% (2.38–6.75) |

The LLM-bound point estimate is below the 5% target, but its bootstrap interval crosses 5%; this run does not justify an unqualified “target met” statement. The timed region is host graph execution; asynchronous delivery is excluded by design, while successful live ingestion and final queue drainage verify the transport path.

Event-to-WebSocket latency was probed with 300 samples per condition. The two full-stack load trials both miss the <200 ms p95 target.

| Condition | Redis state | p50 | p95 | p99 | Probe errors |
|---|---|---:|---:|---:|---:|
| Compose idle | persisted DB 0 | 63.0 ms | 78.0 ms | 94.0 ms | 0 |
| Compose idle | initially empty DB 14 | 62.0 ms | 63.0 ms | 78.0 ms | 0 |
| Compose, 50 users | persisted DB 0 | 594.0 ms | 1312.0 ms | 1766.4 ms | 0 |
| Compose, 50 users | initially empty DB 14 | 235.0 ms | 1642.5 ms | 2516.2 ms | 0 |
| Read-path control, 50 users | backend DB 13; worker DB 14 | 141.0 ms | 625.7 ms | 782.5 ms | 0 |

| Locust condition | Requests | Failures | Throughput | Mean | Aggregate p95 |
|---|---:|---:|---:|---:|---:|
| Full stack, persisted DB 0 | 4,951 | 0 | 78.78 req/s | 566.8 ms | 1400 ms |
| Full stack, initially empty DB 14 | 4,371 | 1 | 69.50 req/s | 489.4 ms | 1600 ms |
| Read-path control | 8,135 | 0 | 132.50 req/s | 241.7 ms | 720 ms |

The sole isolated-run Locust failure was an unauthenticated request that returned 502 instead of the expected 401 during saturation; aggregate failure rate was 0.02%. During the clean DB 14 run, the database grew to 2,832 events, 1,157 anomaly records, and 650 traces. The detector keys Failure Loops history only by agent, while the load generator deliberately reuses one agent identity and a small set of names across many traces. In addition, each history response scans the complete anomaly stream. The read-path control nearly doubled throughput (1.91×) and reduced probe p95 by 61.9%, supporting this detector/read-path interaction as a major bottleneck. Because the control still measured 625.7 ms p95, it is not the only bottleneck.

Evidence: `current_build_overhead_compose.json`, `latency_*_compose*.json`, `latency_50u_readpath_control.json`, and the corresponding `locust_50u_*` CSV/HTML files.

## Stage 4 — Live versus historical convergence

Across nine continuously connected burst runs—10, 50, and 100 spans, three repetitions each, with active and completed versions—the production compose paths matched the complete event multiset and dashboard-equivalent latest state in 9/9 runs. Exact arrival order matched in only 1/9 runs. A likely explanation is the four-worker ingestion path performing stream append and per-trace list insertion as separate Redis operations, allowing the list order used by history to diverge from stream order used by WebSocket delivery. This is an inference from the behavior and code path, not yet a proven causal result.

The reconnect-gap scenario disconnected after ten active events, emitted all ten completions while offline, and then reconnected. Historical replay contained all 20 events; live state contained only the ten active events. All ten latest span states mismatched. This confirms that connecting at Redis `$` without history backfill cannot guarantee convergence after a disconnect.

The preliminary single-process fallback matched order in 9/9 continuous runs. Its contrast with the four-worker production result shows why it cannot substitute for compose evidence: it masked the production ordering race.

Evidence: `live_history_convergence_compose.json` (authoritative) and `live_history_convergence_fallback.json` (preliminary diagnostic).

## Findings to resolve before the comparison

1. Key Failure Loops state by at least `(trace_id, agent_id)` and deduplicate span lifecycle versions by `span_id`, then rerun the unchanged held-out corpus.
2. Add a per-trace anomaly index or otherwise avoid full anomaly-stream scans in every history request, then repeat the isolated 50-user test.
3. Make history ordering consistent with Redis stream order—atomically maintain the trace index or sort from authoritative Redis message IDs—and repeat the burst protocol.
4. Add reconnect catch-up using a last-seen stream ID or history reconciliation, then repeat the reconnect-gap protocol.
5. Pin container dependencies used by the evaluation; the current Docker build resolved current package versions and is not fully immutable.
6. Repeat overhead and load tests after the fixes. Only then begin the pre-registered three-way comparison.

## Reproduction commands

```text
python scripts/evaluation/novelty_evaluation.py --output manuscript/evaluation-artifacts/2026-08-30-current-build/novelty_evaluation.json
python scripts/evaluation/anomaly_validation.py --output manuscript/evaluation-artifacts/2026-08-30-current-build/anomaly_validation.json
python scripts/evaluation/current_build_overhead.py --delivery-transport live --runs 30 --warmup 5 --output manuscript/evaluation-artifacts/2026-08-30-current-build/current_build_overhead_compose.json
python scripts/evaluation/live_history_convergence.py --output manuscript/evaluation-artifacts/2026-08-30-current-build/live_history_convergence_compose.json
python infra/loadtest/event_latency_probe.py --samples 300 --concurrency 5 --json-output <artifact.json>
```

The comparison command was intentionally not invoked.
