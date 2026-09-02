"""Counterbalanced paired SDK-overhead benchmark for the current checkout."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

import httpx

from common import (
    REPO_ROOT,
    add_repo_paths,
    bootstrap_mean_ci,
    distribution,
    environment_manifest,
    write_json,
)

add_repo_paths()
sys.path.insert(0, str(REPO_ROOT / "examples" / "langgraph_demo_agent"))

from branching_agent import build_branching_graph
from agentscope import LangGraphAdapter
from agentscope.sender import sender


SEED = 20260830
QUERIES = ("Calculate 42 * 10", "Search system status", "Tell me a joke")


def build_delayed_branching_graph(node_delay_s: float):
    if node_delay_s <= 0:
        return build_branching_graph()

    import time as blocking_time
    from typing_extensions import TypedDict
    from langgraph.graph import END, START, StateGraph
    import branching_agent as demo

    class BranchingState(TypedDict):
        query: str
        route: str
        result: str

    def delayed(function):
        def wrapper(state):
            blocking_time.sleep(node_delay_s)
            return function(state)

        return wrapper

    builder = StateGraph(BranchingState)
    builder.add_node("router", delayed(demo.router_node))
    builder.add_node("calculator", delayed(demo.calculator_node))
    builder.add_node("search", delayed(demo.search_node))
    builder.add_node("general", delayed(demo.general_node))
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        demo.select_route,
        {"calculator": "calculator", "search": "search", "general": "general"},
    )
    builder.add_edge("calculator", END)
    builder.add_edge("search", END)
    builder.add_edge("general", END)
    return builder.compile()


async def _measure(graph, state: dict, instrumented: bool, trace_id: str) -> float:
    config = None
    if instrumented:
        config = {"callbacks": [LangGraphAdapter(agent_id="benchmark-agent", trace_id=trace_id)]}
    started = time.perf_counter_ns()
    if config:
        await graph.ainvoke(dict(state), config=config)
    else:
        await graph.ainvoke(dict(state))
    return (time.perf_counter_ns() - started) / 1_000_000.0


async def _configuration(label: str, delay: float, runs: int, warmup: int) -> dict:
    rng = random.Random(SEED + int(delay * 1_000_000))
    rows = []
    for pair_index in range(warmup + runs):
        query = QUERIES[pair_index % len(QUERIES)]
        graph = build_delayed_branching_graph(delay)
        state = {"query": query, "route": "", "result": ""}
        order = [False, True]
        rng.shuffle(order)
        timings = {}
        for instrumented in order:
            key = "instrumented" if instrumented else "baseline"
            timings[key] = await _measure(
                graph,
                state,
                instrumented,
                f"overhead-{label}-{pair_index}",
            )
        if pair_index >= warmup:
            baseline = timings["baseline"]
            instrumented = timings["instrumented"]
            rows.append(
                {
                    "pair_index": pair_index - warmup,
                    "query": query,
                    "order": "AB" if order == [False, True] else "BA",
                    "baseline_ms": baseline,
                    "instrumented_ms": instrumented,
                    "paired_difference_ms": instrumented - baseline,
                    "paired_overhead_percent": (instrumented - baseline) / baseline * 100.0,
                }
            )

    differences = [row["paired_difference_ms"] for row in rows]
    overheads = [row["paired_overhead_percent"] for row in rows]
    return {
        "label": label,
        "simulated_node_delay_ms": delay * 1000.0,
        "runs": runs,
        "warmup_pairs_discarded": warmup,
        "order_counts": dict(
            (order, sum(row["order"] == order for row in rows)) for order in ("AB", "BA")
        ),
        "baseline_ms": distribution([row["baseline_ms"] for row in rows]),
        "instrumented_ms": distribution([row["instrumented_ms"] for row in rows]),
        "paired_difference_ms": {
            **distribution(differences),
            "mean_bootstrap_95": bootstrap_mean_ci(differences),
        },
        "paired_overhead_percent": {
            **distribution(overheads),
            "mean_bootstrap_95": bootstrap_mean_ci(overheads),
        },
        "raw_pairs": rows,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument(
        "--delivery-transport",
        choices=("mock", "live"),
        default="mock",
        help="Use deterministic HTTP 202 delivery or the configured live ingest endpoint.",
    )
    args = parser.parse_args()
    if args.delivery_transport == "mock":
        # Delivery is outside the timed region. A deterministic success
        # transport still exercises queue consumption, redaction,
        # serialization, headers, and async HTTP dispatch.
        async def accepted(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(202, json={"status": "accepted"})

        await sender.client.aclose()
        sender.client = httpx.AsyncClient(transport=httpx.MockTransport(accepted), timeout=5.0)
    payload = {
        "study": "current_build_sdk_overhead",
        "manifest": environment_manifest(SEED, " ".join(sys.argv)),
        "design": {
            "paired": True,
            "counterbalanced": True,
            "outlier_removal": False,
            "timed_region": "host graph ainvoke; asynchronous delivery excluded by design",
            "delivery_transport": (
                "httpx MockTransport returning HTTP 202"
                if args.delivery_transport == "mock"
                else "live configured AgentScope ingest endpoint"
            ),
            "ingest_url": os.environ.get("AGENTSCOPE_INGEST_URL", "http://localhost:8000/ingest"),
        },
        "configurations": [
            await _configuration("cpu_trivial", 0.0, args.runs, args.warmup),
            await _configuration("llm_bound_100ms_per_node", 0.1, args.runs, args.warmup),
        ],
    }
    try:
        await asyncio.wait_for(sender.queue.join(), timeout=30.0)
        payload["sender_queue_drained"] = True
    except asyncio.TimeoutError:
        payload["sender_queue_drained"] = False
    write_json(args.output, payload)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "overhead": {
                    config["label"]: config["paired_overhead_percent"]["mean"]
                    for config in payload["configurations"]
                },
            }
        )
    )
    await sender.client.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
