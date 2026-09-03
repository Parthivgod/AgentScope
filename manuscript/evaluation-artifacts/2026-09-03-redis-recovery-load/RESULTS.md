# Redis Recovery and Latency Profile

## Frozen condition

The CI/reconnection candidate was frozen at commit `dadf573`. Each main 50-user repetition used a fresh Redis volume, 75 seconds of mixed Locust traffic, and 300 event probes paced across 60 seconds. No trial or failure was discarded.

## Observations

| Condition | Repetition | Requests | Failures | Requests/s | HTTP p95 | Event p50 | Event p95 | Event p99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mixed 10 users | 1 | 5,320 | 0 | 112.37 | 100.0 ms | 47.0 ms | 78.0 ms | 94.0 ms |
| mixed 25 users | 1 | 10,838 | 0 | 231.59 | 170.0 ms | 47.0 ms | 125.0 ms | 212.9 ms |
| mixed 50 users | 1 | 22,366 | 0 | 303.68 | 280.0 ms | 62.0 ms | 219.7 ms | 297.1 ms |
| mixed 50 users | 2 | 12,412 | 0 | 165.01 | 540.0 ms | 78.0 ms | 656.8 ms | 1563.6 ms |
| mixed 50 users | 3 | 25,144 | 0 | 333.87 | 280.0 ms | 94.0 ms | 250.7 ms | 328.0 ms |
| ingest-only 50 users | 1 | 30,284 | 0 | 409.31 | 120.0 ms | 47.0 ms | 47.0 ms | 63.0 ms |

The three mixed 50-user event-p95 values averaged 375.77 ms (process-level t 95% CI -230.05–981.59 ms); all exceeded the 200 ms target. Run 2 is retained despite its pronounced host/runtime slowdown.

The 50-user ingest-only control completed 30,284 requests with zero failures, HTTP p95 120 ms, and event p95 47 ms. Mixed traffic passed at 10 users (78 ms) and 25 users (125 ms), then missed at 50 users. Within the 50-user runs, later windows were generally slower than early windows.

## Profile interpretation

Endpoint and container telemetry associated the miss with growing historical-read work: `GET /history` had the highest endpoint tail latency, and the backend approached its two-core limit in the higher-throughput repetitions. The pre-optimization endpoint expanded every history request into one Redis `XRANGE` command per indexed event. This is workload-level causal-control evidence, not a component-level causal estimate; the post-optimization rerun is reported separately.

## Artifacts

Raw Locust CSV/logs, paced probe records, per-second container samples, `profile_summary.json`, `table_latency_profile.csv`, and the PNG/PDF figure are retained in this directory.
