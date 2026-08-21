"""
Week 9 SDK overhead benchmark (NFR 9.5, PRD §10 Test #5).

Runs the actual `examples/langgraph_demo_agent` branching graph workload
with and without the AgentScope SDK attached (LangGraphAdapter + sender),
using N paired, interleaved runs (baseline, instrumented, baseline, ...)
to control for drift. Reports the measured overhead — whatever it is.

The timed quantity is the host agent's `graph.ainvoke()` wall time: the
cost the SDK adds to the monitored agent's execution. Span delivery is
asynchronous (fail-silent sender), so network latency does not block the
timed region; only span construction, queueing, and callback dispatch are
included, which is exactly the overhead the SDK imposes on the host.

Usage:
    AGENTSCOPE_API_KEY=test-key AGENTSCOPE_INGEST_URL=http://localhost:8000/ingest \
        python week9_overhead_benchmark.py [--runs 30]
"""

import argparse
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "examples" / "langgraph_demo_agent"))

from branching_agent import build_branching_graph  # noqa: E402
from agentscope import LangGraphAdapter  # noqa: E402
from agentscope.sender import sender  # noqa: E402

QUERIES = ["Calculate 42 * 10", "Search system status", "Tell me a joke"]


def build_delayed_branching_graph(node_delay_s: float):
    """Same branching-graph structure, with each node sleeping `node_delay_s`
    to simulate realistic LLM-call latency. Used for the second benchmark
    configuration: relative overhead on an LLM-bound workload, which is the
    workload class NFR 9.5's <5% target was written for.
    """
    import time as _time
    from typing import Any, Dict
    from typing_extensions import TypedDict
    from langgraph.graph import StateGraph, START, END

    class BranchingState(TypedDict):
        query: str
        route: str
        result: str

    def delayed(fn):
        def wrapper(state):
            _time.sleep(node_delay_s)
            return fn(state)
        return wrapper

    import branching_agent as _ba

    builder = StateGraph(BranchingState)
    builder.add_node("router", delayed(_ba.router_node))
    builder.add_node("calculator", delayed(_ba.calculator_node))
    builder.add_node("search", delayed(_ba.search_node))
    builder.add_node("general", delayed(_ba.general_node))
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router", _ba.select_route,
        {"calculator": "calculator", "search": "search", "general": "general"},
    )
    builder.add_edge("calculator", END)
    builder.add_edge("search", END)
    builder.add_edge("general", END)
    return builder.compile()


async def run_pair(node_delay_s: float = 0.0) -> tuple[float, float]:
    """One interleaved (baseline, instrumented) timing pair, in seconds."""
    graph = build_delayed_branching_graph(node_delay_s) if node_delay_s > 0 else build_branching_graph()
    state = {"query": QUERIES[run_pair.query_index % len(QUERIES)], "route": "", "result": ""}
    run_pair.query_index += 1

    t0 = time.perf_counter()
    await graph.ainvoke(dict(state))
    t1 = time.perf_counter()
    baseline = t1 - t0

    adapter = LangGraphAdapter(agent_id="benchmark-agent", trace_id="trace-benchmark-w9")
    t0 = time.perf_counter()
    await graph.ainvoke(dict(state), config={"callbacks": [adapter]})
    t1 = time.perf_counter()
    instrumented = t1 - t0

    return baseline, instrumented


run_pair.query_index = 0


async def run_config(label: str, runs: int, warmup: int, node_delay_s: float) -> None:
    print(f"\n--- Configuration: {label} ({runs} paired runs, {warmup} warmup pairs discarded) ---")
    print(f"  ingest url: {os.environ.get('AGENTSCOPE_INGEST_URL', 'http://localhost:8000/ingest')}")

    pairs: list[tuple[float, float]] = []
    for i in range(warmup + runs):
        pair = await run_pair(node_delay_s)
        if i >= warmup:
            pairs.append(pair)
        if (i + 1) % 5 == 0 or i == 0:
            print(f"  run {i + 1:>3}/{warmup + runs}: baseline={pair[0]*1000:8.2f}ms  instrumented={pair[1]*1000:8.2f}ms")

    report(pairs)


def report(pairs: list[tuple[float, float]]) -> None:
    baselines = [b for b, _ in pairs]
    instrumented = [s for _, s in pairs]
    diffs = [s - b for b, s in pairs]
    overhead_pcts = [(s - b) / b * 100.0 for b, s in pairs]

    def ms(x):
        return f"{x * 1000:.3f}ms"

    print("\n=== Results (measured; no outlier removal) ===")
    print(f"  baseline      mean={ms(statistics.mean(baselines))}  median={ms(statistics.median(baselines))}  stdev={ms(statistics.stdev(baselines))}")
    print(f"  instrumented  mean={ms(statistics.mean(instrumented))}  median={ms(statistics.median(instrumented))}  stdev={ms(statistics.stdev(instrumented))}")
    print(f"  paired diff   mean={ms(statistics.mean(diffs))}  median={ms(statistics.median(diffs))}  stdev={ms(statistics.stdev(diffs))}")
    print(f"  overhead pct  mean={statistics.mean(overhead_pcts):+.2f}%  median={statistics.median(overhead_pcts):+.2f}%  min={min(overhead_pcts):+.2f}%  max={max(overhead_pcts):+.2f}%")


async def main(runs: int, warmup: int) -> None:
    print(f"Week 9 SDK overhead benchmark (NFR 9.5 / Test #5)")
    # Config 1: the actual demo workload as-is (CPU-trivial, ~5-7ms/graph).
    await run_config("demo branching graph as-is", runs, warmup, node_delay_s=0.0)
    # Config 2: same graph with 100ms simulated LLM latency per node (~300ms/graph),
    # the LLM-bound workload class NFR 9.5's <5% target addresses.
    await run_config("branching graph, 100ms simulated LLM latency per node", runs, warmup, node_delay_s=0.1)

    # Give the fail-silent sender a moment to drain queued spans out of process.
    try:
        await asyncio.wait_for(sender.queue.join(), timeout=30.0)
    except asyncio.TimeoutError:
        print("  note: sender queue did not drain within 30s (non-fatal for timing)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(main(args.runs, args.warmup))
