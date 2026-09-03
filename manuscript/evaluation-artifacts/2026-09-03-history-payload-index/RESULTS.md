# History Payload-Index Evaluation

## Protocol

The before condition was frozen at `dadf573`; the payload-index candidate was frozen at `7f89f34`. Each condition used three sequential fresh-volume repetitions with 50 Locust users for 75 seconds and 300 ingest-to-WebSocket probes paced across 60 seconds. Raw failures and the high-variance pre run were retained.

## Run-level observations

| Phase | Rep | Requests | Failures | Requests/s | HTTP p95 | Event p50 | Event p95 | Event p99 | Backend CPU mean/max | Redis peak memory |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pre | 1 | 22,366 | 0 | 303.68 | 280.0 ms | 62.0 ms | 219.7 ms | 297.1 ms | 140.2/203.7% | 20.0 MB |
| pre | 2 | 12,412 | 0 | 165.01 | 540.0 ms | 78.0 ms | 656.8 ms | 1563.6 ms | 106.3/201.1% | 12.9 MB |
| pre | 3 | 25,144 | 0 | 333.87 | 280.0 ms | 94.0 ms | 250.7 ms | 328.0 ms | 164.3/204.5% | 22.1 MB |
| post | 1 | 25,889 | 0 | 343.99 | 140.0 ms | 47.0 ms | 125.0 ms | 203.2 ms | 133.8/202.8% | 29.3 MB |
| post | 2 | 30,256 | 0 | 400.68 | 150.0 ms | 47.0 ms | 156.8 ms | 219.3 ms | 158.4/208.9% | 34.5 MB |
| post | 3 | 30,010 | 0 | 397.71 | 130.0 ms | 47.0 ms | 125.0 ms | 172.0 ms | 154.6/201.1% | 35.8 MB |

## Result

Before the payload index, mean event p95 was 375.77 ms (process-level t 95% CI -230.05–981.59); all three runs missed the 200 ms target. After the change, run-level event p95 was 125.0, 156.8, 125.0 ms and the mean was 135.60 ms (t 95% CI 89.99–181.21). All three post-change runs met the target.

The associated mean changes were -63.9% event p95, -61.8% mixed-HTTP p95, and +42.3% throughput. Post-change mean HTTP p95 was 140.00 ms and mean throughput was 380.79 requests/s. Across the three post runs there were zero Locust failures and zero probe errors.

The payload copy increased Redis memory use; post-run peaks were 29.3–35.8 MB while processing more requests, versus 12.9–22.1 MB before. This is the explicit space-for-read-latency tradeoff.

## Boundary

The repetitions were sequential, not randomized interleaved pairs. Changes are associated with the combined payload-index candidate and do not establish universal production performance or a component-level causal effect.
