# Replicated Post-Fix Evaluation

## Observation protocol

The frozen implementation candidate is commit `80ae5b6`. The load protocol used three independent 75-second, 50-user Locust runs, each from a newly created Redis volume. A 300-sample ingest-to-WebSocket probe was evenly scheduled across 60 seconds of each loaded interval. The three-way comparison used three fresh Python processes and fresh product storage stacks per product, 30 measured paired invocations per workload after five warm-ups, no outlier removal, and exact pinned container images.

Uncertainty below is a two-sided Student t 95% confidence interval over the three independent process/run means. With only three repetitions these intervals are low-powered and can be very wide. Within-process bootstrap intervals remain in the raw JSON but are not substituted for process-level replication.

## Loaded latency and reliability

| Repetition | Requests | Failures | Requests/s | HTTP p95 (ms) | Event p50 (ms) | Event p95 (ms) | Event p99 (ms) | Event samples/errors |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 23,095 | 0 | 311.58 | 250.0 | 63.00 | 235.75 | 328.15 | 300/0 |
| 2 | 25,803 | 0 | 342.49 | 320.0 | 109.00 | 266.00 | 375.15 | 300/0 |
| 3 | 28,432 | 0 | 377.34 | 260.0 | 78.00 | 218.05 | 281.01 | 300/0 |

Mean event p95 was 239.93 (179.70 to 300.17) ms; all three run-level values exceeded the 200 ms target. Mean mixed-HTTP p95 was 276.67 (182.62 to 370.71) ms and mean throughput was 343.80 (262.08 to 425.53) requests/s. Across 77,330 requests and 900 event probes, the recorded HTTP and probe error counts were both zero.

The earlier one-run 78 ms p95 observation is therefore not reproducible under this longer whole-window protocol and must not support a general under-load target claim.

## Three-way execution overhead

| Product | Workload | Process reps | Paired trials | Mean overhead %, t 95% CI | Mean absolute delta ms, t 95% CI |
|---|---|---:|---:|---:|---:|
| AgentScope | CPU-trivial | 3 | 90 | 68.92 (39.16 to 98.69) | 2.230 (-0.043 to 4.503) |
| AgentScope | 100 ms/node | 3 | 90 | 4.81 (1.28 to 8.33) | 10.155 (2.546 to 17.765) |
| Langfuse | CPU-trivial | 3 | 90 | 235.36 (107.58 to 363.13) | 5.631 (0.629 to 10.633) |
| Langfuse | 100 ms/node | 3 | 90 | 5.24 (0.54 to 9.93) | 10.848 (0.950 to 20.746) |
| Phoenix | CPU-trivial | 3 | 90 | 647.78 (-283.51 to 1579.07) | 15.545 (7.353 to 23.737) |
| Phoenix | 100 ms/node | 3 | 90 | 6.56 (4.33 to 8.79) | 13.551 (8.873 to 18.228) |

The CPU-trivial percentage is unstable because millisecond-scale absolute costs divide by a very small baseline; it should not be treated as representative of LLM-dominated systems. The 100 ms/node results are the more interpretable overhead condition. Run-to-run intervals overlap substantially, so these three repetitions do not establish a reliable product ranking.

## Resource, visibility, and query observations

| Product | Process CPU s | Peak process RSS MB | Host network MB | Post-flush visibility ms | Native query p95 ms | Verified traces |
|---|---:|---:|---:|---:|---:|---:|
| AgentScope | 27.15 | 97.3 | 0.152 | 280.50 | 57.73 | 210 |
| Langfuse | 18.36 | 124.1 | 0.157 | 648.00 | 176.43 | 210 |
| Phoenix | 18.79 | 109.4 | 0.293 | 739.12 | 49.36 | 210 |

CPU and RSS cover only the comparison Python process, not each product's server containers. Network values use host-wide counters and can include unrelated traffic. Query measurements use each product's native trace-catalog/count endpoint, whose semantics and storage paths differ; they are operational observations, not an apples-to-apples query benchmark. Post-flush visibility is batch-level time from exporter flush completion until all 70 expected traces were query-visible, not per-trace end-to-end latency.

## Claim boundary

The evidence supports exact ingestion completeness (210/210 expected traces per product across three fresh processes) and reports measured local overhead, resources, visibility, query latency, and loaded event latency. It does not establish production generalization, overall product superiority, server-side resource efficiency, or causality for the observed performance differences.

## Generated artifacts

- `table_load_replications.csv`
- `table_three_way_summary.csv`
- `table_resource_and_visibility_summary.csv`
- `figure_load_latency.png` and `.pdf`
- `figure_three_way_overhead.png` and `.pdf`
- `figure_visibility_and_query.png` and `.pdf`
- `aggregate_results.json` and `manifest.json`
