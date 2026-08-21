# AgentScope SDK — Overhead Benchmark

Measurement harness for evaluating AgentScope SDK performance overhead against **NFR 9.5 (<5% overhead target, PRD §10 Test #5)**.

## Week 9 benchmark (executed 2026-08-21)

`week9_overhead_benchmark.py` runs the actual `examples/langgraph_demo_agent` branching graph with and without the SDK attached (`LangGraphAdapter` + fail-silent async sender), using 30 paired interleaved runs (5 warmup pairs discarded), same inputs, no outlier removal. Timed quantity: the host agent's `graph.ainvoke()` wall time.

Two configurations, both measured against the local stack:

1. **Demo workload as-is** (CPU-trivial, ~4.7ms/graph): overhead **+3.3ms mean absolute (+79.7% mean / +60.7% median relative)**. The <5% target is not applicable to this workload — the graph itself is so fast that any instrumentation dominates. Flagged per RULES.md §6: this is the measured number, not the target.
2. **LLM-bound workload** (same graph, 100ms simulated LLM latency per node, ~208ms/graph): overhead **+3.6ms mean absolute (+1.76% mean and median relative)**. This is the workload class NFR 9.5's <5% target addresses, and the measured value meets it.

Consistent absolute SDK cost across both configurations: ~3.3–3.6ms per graph invocation (span construction, callback dispatch, queueing; delivery is async and off the timed path).

Raw run logs: `results/`.

## Running

```bash
cd sdk/agentscope/benchmarks
AGENTSCOPE_API_KEY=test-key AGENTSCOPE_INGEST_URL=http://localhost:8000/ingest \
    python week9_overhead_benchmark.py --runs 30 --warmup 5
```

The Week 5 scaffold (`overhead_benchmark.py`) remains available for synthetic timing runs.
