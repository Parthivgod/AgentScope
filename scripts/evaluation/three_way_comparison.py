"""Matched current-build comparison: AgentScope, Langfuse, and Phoenix.

Each invocation evaluates one tool in a fresh Python process so global
OpenTelemetry instrumentation cannot leak between products. Every tool uses
the same deterministic LangGraph workload, query sequence, warm-up count, and
measured trial count. A no-instrumentation reference is measured in the same
process and raw paired trials are retained.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
import uuid
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import httpx

from common import bootstrap_mean_ci, distribution, environment_manifest, write_json


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "examples" / "langgraph_demo_agent"))
sys.path.insert(0, str(REPO / "sdk"))

from branching_agent import build_branching_graph  # noqa: E402
from agentscope import LangGraphAdapter  # noqa: E402


SEED = 20260831
QUERIES = ("Calculate 42 * 10", "Search system status", "Tell me a joke")


def build_delayed_branching_graph(node_delay_s: float):
    import time as _time
    from typing import Dict
    from typing_extensions import TypedDict
    from langgraph.graph import END, START, StateGraph
    import branching_agent as graph_nodes

    class State(TypedDict):
        query: str
        route: str
        result: str

    def delayed(fn):
        def wrapper(state):
            _time.sleep(node_delay_s)
            return fn(state)
        return wrapper

    builder = StateGraph(State)
    builder.add_node("router", delayed(graph_nodes.router_node))
    builder.add_node("calculator", delayed(graph_nodes.calculator_node))
    builder.add_node("search", delayed(graph_nodes.search_node))
    builder.add_node("general", delayed(graph_nodes.general_node))
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        graph_nodes.select_route,
        {"calculator": "calculator", "search": "search", "general": "general"},
    )
    builder.add_edge("calculator", END)
    builder.add_edge("search", END)
    builder.add_edge("general", END)
    return builder.compile()


def graph_for(delay_s: float):
    return build_delayed_branching_graph(delay_s) if delay_s else build_branching_graph()


async def timed_invoke(graph, index: int, callback=None) -> float:
    state = {"query": QUERIES[index % len(QUERIES)], "route": "", "result": ""}
    config = {"callbacks": [callback]} if callback is not None else None
    started = time.perf_counter()
    await graph.ainvoke(state, config=config)
    return (time.perf_counter() - started) * 1000.0


def package_versions() -> dict[str, str | None]:
    result = {}
    for package in (
        "langfuse",
        "openinference-instrumentation-langchain",
        "opentelemetry-sdk",
        "opentelemetry-exporter-otlp-proto-grpc",
        "langgraph",
        "langchain-core",
    ):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = None
    return result


async def snapshot_agentscope() -> int:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(os.environ.get("AGENTSCOPE_BASE_URL", "http://localhost") + "/traces")
        response.raise_for_status()
        return len(response.json()["trace_ids"])


async def snapshot_langfuse() -> int:
    base = os.environ.get("LANGFUSE_BASE_URL", "http://localhost:3000")
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    trace_ids: set[str] = set()
    cursor: str | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params: dict[str, str | int] = {"limit": 1000, "fields": "basic"}
            if cursor:
                params["cursor"] = cursor
            response = await client.get(
                base.rstrip("/") + "/api/public/v2/observations", params=params, auth=auth
            )
            response.raise_for_status()
            payload = response.json()
            trace_ids.update(row["traceId"] for row in payload.get("data", []))
            cursor = payload.get("meta", {}).get("cursor")
            if not cursor:
                return len(trace_ids)


async def snapshot_phoenix() -> int:
    endpoint = os.environ.get("PHOENIX_HTTP_ENDPOINT", "http://localhost:6006")
    query = {"query": "{ projects { edges { node { traceCount } } } }"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(endpoint.rstrip("/") + "/graphql", json=query)
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(f"Phoenix GraphQL verification failed: {payload['errors']}")
        return sum(edge["node"]["traceCount"] for edge in payload["data"]["projects"]["edges"])


async def snapshot(arm: str) -> int:
    return await {
        "agentscope": snapshot_agentscope,
        "langfuse": snapshot_langfuse,
        "phoenix": snapshot_phoenix,
    }[arm]()


def initialize_phoenix():
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk import trace as sdk_trace
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from openinference.instrumentation.langchain import LangChainInstrumentor

    endpoint = os.environ.get("PHOENIX_GRPC_ENDPOINT", "localhost:4317")
    provider = sdk_trace.TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
    LangChainInstrumentor().instrument()
    return provider


def callback_for(arm: str, label: str, index: int):
    if arm == "agentscope":
        return LangGraphAdapter(
            agent_id="comparison-agent",
            trace_id=f"comparison-{label}-{index}-{uuid.uuid4().hex[:8]}",
        )
    if arm == "langfuse":
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    return None


async def flush(arm: str, phoenix_provider=None) -> None:
    if arm == "agentscope":
        from agentscope.sender import sender
        await asyncio.wait_for(sender.queue.join(), timeout=60.0)
    elif arm == "langfuse":
        from langfuse import get_client
        get_client().flush()
    elif arm == "phoenix":
        if not phoenix_provider.force_flush(timeout_millis=60_000):
            raise RuntimeError("Phoenix OpenTelemetry exporter did not flush")


def summarize_configuration(label: str, delay_s: float, runs: int, warmup: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    differences = []
    percentages = []
    for row in rows:
        row["difference_ms"] = row["instrumented_ms"] - row["baseline_ms"]
        row["overhead_percent"] = row["difference_ms"] / row["baseline_ms"] * 100.0
        differences.append(row["difference_ms"])
        percentages.append(row["overhead_percent"])
    return {
        "label": label,
        "simulated_node_delay_ms": delay_s * 1000.0,
        "runs": runs,
        "warmup_pairs_discarded": warmup,
        "order_counts": {order: sum(row["order"] == order for row in rows) for order in sorted({r["order"] for r in rows})},
        "baseline_ms": distribution([row["baseline_ms"] for row in rows]),
        "instrumented_ms": distribution([row["instrumented_ms"] for row in rows]),
        "paired_difference_ms": {
            **distribution(differences),
            "mean_bootstrap_95": bootstrap_mean_ci(differences, seed=SEED),
        },
        "paired_overhead_percent": {
            **distribution(percentages),
            "mean_bootstrap_95": bootstrap_mean_ci(percentages, seed=SEED),
        },
        "raw_pairs": rows,
    }


async def run_configuration(arm: str, label: str, delay_s: float, runs: int, warmup: int) -> dict[str, Any]:
    plain_graph = graph_for(delay_s)
    instrumented_graph = graph_for(delay_s)
    rows = []
    rng = random.Random(SEED + sum(map(ord, arm + label)))
    for index in range(warmup + runs):
        callback = callback_for(arm, label, index)
        order = rng.choice(("AB", "BA"))
        if order == "AB":
            base_ms = await timed_invoke(plain_graph, index)
            tool_ms = await timed_invoke(instrumented_graph, index, callback)
        else:
            tool_ms = await timed_invoke(instrumented_graph, index, callback)
            base_ms = await timed_invoke(plain_graph, index)
        if index >= warmup:
            rows.append({
                "pair_index": index - warmup,
                "query": QUERIES[index % len(QUERIES)],
                "order": order,
                "baseline_ms": base_ms,
                "instrumented_ms": tool_ms,
            })

    await flush(arm)
    return summarize_configuration(label, delay_s, runs, warmup, rows)


async def run_phoenix_configurations(runs: int, warmup: int) -> list[dict[str, Any]]:
    definitions = (("cpu_trivial", 0.0), ("llm_bound_100ms_per_node", 0.1))
    baselines: dict[str, list[float]] = {}
    instrumented_graphs = {}
    for label, delay_s in definitions:
        plain = graph_for(delay_s)
        instrumented_graphs[label] = graph_for(delay_s)
        baselines[label] = [await timed_invoke(plain, index) for index in range(warmup + runs)]

    provider = initialize_phoenix()
    results = []
    for label, delay_s in definitions:
        measured = [
            await timed_invoke(instrumented_graphs[label], index)
            for index in range(warmup + runs)
        ]
        rows = []
        for index, (base_ms, tool_ms) in enumerate(zip(baselines[label][warmup:], measured[warmup:])):
            rows.append({
                "pair_index": index,
                "query": QUERIES[(warmup + index) % len(QUERIES)],
                "order": "baseline_then_instrumented",
                "baseline_ms": base_ms,
                "instrumented_ms": tool_ms,
            })
        results.append(summarize_configuration(label, delay_s, runs, warmup, rows))
    await flush("phoenix", provider)
    return results


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, choices=("agentscope", "langfuse", "phoenix"))
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    before = await snapshot(args.arm)
    configurations = (
        await run_phoenix_configurations(args.runs, args.warmup)
        if args.arm == "phoenix"
        else [
            await run_configuration(args.arm, "cpu_trivial", 0.0, args.runs, args.warmup),
            await run_configuration(args.arm, "llm_bound_100ms_per_node", 0.1, args.runs, args.warmup),
        ]
    )
    after = before
    for _ in range(30):
        await asyncio.sleep(2.0)
        after = await snapshot(args.arm)
        if after > before:
            break
    if after <= before:
        raise RuntimeError(f"{args.arm} ingestion was not verified: count stayed {before} -> {after}")

    payload = {
        "study": "agentscope_langfuse_phoenix_matched_comparison",
        "arm": args.arm,
        "manifest": environment_manifest(SEED, " ".join(sys.argv)),
        "comparison_packages": package_versions(),
        "design": {
            "workload": "same deterministic branching LangGraph; router plus one specialist",
            "capture_policy": "full input/output capture",
            "runs_per_configuration": args.runs,
            "warmup_pairs_discarded": args.warmup,
            "outlier_removal": False,
            "timed_region": "graph ainvoke; asynchronous exporter flush excluded",
            "phoenix_order_limitation": "global instrumentation requires baseline phase before Phoenix phase",
        },
        "verified_ingestion": {"before_trace_count": before, "after_trace_count": after, "delta": after - before},
        "configurations": configurations,
    }
    write_json(args.output, payload)
    print(json.dumps({
        "arm": args.arm,
        "output": str(args.output),
        "verified_trace_delta": after - before,
        "mean_overhead_percent": {
            row["label"]: row["paired_overhead_percent"]["mean"] for row in configurations
        },
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
