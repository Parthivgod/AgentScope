# Evaluation Results

This section reports the latest evidence available on 2026-09-03. Every numerical claim is tied to a repository artifact. PRD thresholds are identified as targets rather than silently converted into achieved results. Unless stated otherwise, measurements use the local production Compose path (Nginx, four FastAPI processes, Redis 7, anomaly worker) on Windows 11; no result is an AWS measurement.

## RQ1 — Delegation-context fidelity

All 107 deterministic framework-free delegation scenarios passed exact checks for trace identity, parentage, current owner, delegation chain, and hop count. The set includes 100 concurrent chains plus exception and cancellation restoration cases. This establishes behavior for the tested Python execution contexts, not universal compatibility with every agent runtime.

## RQ2 — Anomaly detection

The frozen 1,200-case synthetic corpus contains separate 600-case tuning and 600-case held-out splits. Each rule has 50 positive and 50 negative held-out cases.

| Rule | TP | TN | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Crashes | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| Failure Loops | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| Timeouts | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| Token Spikes | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| Message Storms | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| Delegation Cycles | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |

Precision and recall have Wilson 95% intervals of 0.929–1.000. These results meet the declared targets on this synthetic corpus only. Failure Loops improved from pre-fix precision 0.714 and F1 0.833 after state isolation by `(trace_id, agent_id)` and lifecycle deduplication by `span_id`. Source: `evaluation-artifacts/2026-08-31-post-fix/anomaly_validation_postfix.json`.

## RQ3 — Privacy-preserving loop detection

In a balanced 200-case ablation, full capture and HMAC-based redaction each produced 100 TP and 100 TN. Literal-only redaction produced 100 false positives on changing protected values because every input became the same placeholder. A sentinel scan found no raw protected input/output in the serialized wire object. The HMAC secret is process-local and is not transmitted. This is mechanism evidence, not a formal privacy proof. Source: `evaluation-artifacts/2026-08-30-current-build/privacy_ablation.json`.

## RQ4 — Latency and history-read optimization

The 2026-09-03 protocol ran three independent 75-second, 50-user mixed-load repetitions from fresh Redis volumes. Each run used 300 event-to-WebSocket probes paced over 60 seconds. Before the ordered payload index, all three event p95 values missed the 200 ms target; an ingest-only control remained below the target, and profiling identified growing `/history` command amplification.

| Candidate | Run event p95 values (ms) | Mean event p95 | Mean HTTP p95 | Mean throughput |
|---|---|---:|---:|---:|
| Pre-index, `dadf573` | 219.75, 656.80, 250.75 | 375.77 ms | 366.67 ms | 267.52 req/s |
| Payload index, `7f89f34` | 125.00, 156.80, 125.00 | **135.60 ms** | **140.00 ms** | **380.79 req/s** |

All three post-index repetitions were below 200 ms. Relative to the sequential pre-index runs, mean event p95 fell 63.9%, mean HTTP p95 fell 61.8%, and throughput rose 42.3%. The implementation atomically stores a per-trace ordered payload copy and serves complete new traces with one `LRANGE`; legacy or partial indexes use the authoritative Redis-ID fallback. Redis peak memory rose to 29.3–35.8 MB in the post runs while processing more requests, compared with 12.9–22.1 MB before. Because the repetitions were sequential rather than randomized interleaved pairs, the differences are associated with the combined candidate and are not a component-level causal estimate or a universal production guarantee.

Sources: `evaluation-artifacts/2026-09-03-redis-recovery-load/` and `evaluation-artifacts/2026-09-03-history-payload-index/`.

## RQ5 — AgentScope, Langfuse, and Phoenix

The latest matched comparison used three fresh processes and storage stacks per product, 30 measured pairs per workload and process after five warm-ups, full capture, no outlier removal, and 210/210 verified traces per product. Uncertainty is a Student t 95% confidence interval across the three process means.

| Product | CPU-trivial overhead | Absolute delta | 100 ms/node overhead | Absolute delta |
|---|---:|---:|---:|---:|
| AgentScope | 68.92% (39.16–98.69) | 2.230 ms | 4.81% (1.28–8.33) | 10.155 ms |
| Langfuse | 235.36% (107.58–363.13) | 5.631 ms | 5.24% (0.54–9.93) | 10.848 ms |
| Phoenix | 647.78% (-283.51–1579.07) | 15.545 ms | 6.56% (4.33–8.79) | 13.551 ms |

CPU-trivial percentages are unstable because millisecond costs divide by very small baselines. The 100 ms/node intervals overlap substantially; three repetitions do not establish a reliable product ranking or an unconditional <5% claim.

| Product | Process CPU | Peak process RSS | Host network | Post-flush visibility | Native query p95 |
|---|---:|---:|---:|---:|---:|
| AgentScope | 27.15 s | 97.3 MB | 0.152 MB | 280.50 ms | 57.73 ms |
| Langfuse | 18.36 s | 124.1 MB | 0.157 MB | 648.00 ms | 176.43 ms |
| Phoenix | 18.79 s | 109.4 MB | 0.293 MB | 739.12 ms | 49.36 ms |

CPU/RSS exclude product server containers, host network counters are not isolated, and native query endpoints are not semantically identical. Visibility is a batch-level post-flush observation. The comparison therefore reports local operational measurements and ingestion completeness, not overall product superiority. Source: `evaluation-artifacts/2026-09-02-replicated/`.

## RQ6 — Convergence, recovery, and security

- Live/history convergence matched event multiset, exact arrival order, and dashboard-equivalent latest state in 9/9 continuously connected production bursts.
- Cursor reconnect delivered all 20 expected lifecycle events in exact order and converged with history while referenced Redis entries remained retained.
- Redis restart accepted 20 events before and 20 after restart, recovered in approximately one second, recorded zero post-restart transient failures, and ended with all 40 events.
- A stalled WebSocket consumer left ingest p50/p95 effectively unchanged: 50/53 ms baseline and 52/55 ms while stalled.
- Worker restart caught up 70 accepted events from its checkpoint. Backend termination left the monitored application successful in 30/30 bounded workloads.
- Missing and invalid API keys are rejected; local TLS and wire-level redaction tests pass.

These are bounded fault-injection results. They do not cover permanent Redis loss, expired/trimmed reconnect cursors, hostile deployment exposure, or every ambiguous retry outcome for non-idempotent commands.

## RQ7 — Usability

The dashboard build, lint, accessibility evidence, and scripted failure-injection rehearsal are complete. The required unfamiliar-human session has not occurred, so no usability finding, completion rate, time-to-diagnosis, or SUS score is reported. The controlled protocol and blank recording instruments are in `docs/usability-test-prep.md` and `manuscript/usability-study/`.

## Threats to validity

The detector corpus and delegation cases are synthetic. Performance runs are local and low-powered at three independent repetitions. The history before/after sequence is not randomized. Competing products expose different storage and query semantics, and server-container resource costs were not captured in the comparison process metrics. Human usability and cloud deployment remain unevaluated. These boundaries prohibit claims of perfect field accuracy, universal production latency, formal privacy, or overall product superiority.
