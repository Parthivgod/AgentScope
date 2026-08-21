"""
Week 10 Track B comparative baseline vs Arize Phoenix (PRD §10 Test #8).

Runs the SAME branching-graph workload (demo-as-is and 100ms/node LLM-bound,
matching Week 9's overhead benchmark configurations) three ways:
  baseline  — no instrumentation
  agentscope — LangGraphAdapter + fail-silent sender -> local AgentScope stack
  phoenix   — OpenInference LangChain global tracer -> local Phoenix (OTLP gRPC)

Paired, interleaved runs; N per configuration; no outlier removal.

Usage: python scripts/baseline-comparison-phoenix.py [--runs 15]
"""

import argparse
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "examples" / "langgraph_demo_agent"))
sys.path.insert(0, str(REPO / "sdk" / "agentscope" / "benchmarks"))

os.environ.setdefault("AGENTSCOPE_API_KEY", "test-key")
os.environ.setdefault("AGENTSCOPE_INGEST_URL", "http://localhost:8000/ingest")
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

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


from branching_agent import build_branching_graph  # noqa: E402
from agentscope import LangGraphAdapter  # noqa: E402


def get_phoenix_tracer():
    # Explicit SDK provider + OTLP gRPC exporter -> local Phoenix. Without
    # this, instrument() uses a ProxyTracerProvider and spans go nowhere
    # (verified: Phoenix traceCount stayed 0 until this was set up).
    from opentelemetry import trace
    from opentelemetry.sdk import trace as sdk_trace
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    provider = sdk_trace.TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint="localhost:4317", insecure=True)))
    trace.set_tracer_provider(provider)
    from openinference.instrumentation.langchain import LangChainInstrumentor
    LangChainInstrumentor().instrument()
    return provider


async def timed_invoke(graph, state, config=None):
    t0 = time.perf_counter()
    await graph.ainvoke(dict(state), config=config)
    return time.perf_counter() - t0


async def run_config(label, runs, warmup, node_delay_s):
    graph_plain = build_delayed_branching_graph(node_delay_s) if node_delay_s else build_branching_graph()
    graph_scope = build_delayed_branching_graph(node_delay_s) if node_delay_s else build_branching_graph()
    graph_phoenix = build_delayed_branching_graph(node_delay_s) if node_delay_s else build_branching_graph()

    # Separate graph objects per arm: Phoenix's global tracer instruments
    # everything once enabled, so measure Phoenix arms last and do not
    # interleave arms — order: all baseline, all agentscope, then enable
    # Phoenix and run phoenix arm. (Global tracers cannot be scoped per call.)
    queries = ["Calculate 42 * 10", "Search system status", "Tell me a joke"]

    def state_for(i):
        return {"query": queries[i % len(queries)], "route": "", "result": ""}

    base, scope = [], []
    for i in range(warmup + runs):
        base.append(await timed_invoke(graph_plain, state_for(i)))
    for i in range(warmup + runs):
        adapter = LangGraphAdapter(agent_id="baseline-cmp", trace_id="trace-baseline-cmp")
        scope.append(await timed_invoke(graph_scope, state_for(i), config={"callbacks": [adapter]}))

    provider = get_phoenix_tracer()
    phx = []
    for i in range(warmup + runs):
        phx.append(await timed_invoke(graph_phoenix, state_for(i)))
    # Flush the OTEL batch exporter BEFORE uninstrumenting so spans genuinely
    # reach Phoenix (otherwise they are dropped and the comparison is invalid).
    provider.force_flush(timeout_millis=30000)
    from openinference.instrumentation.langchain import LangChainInstrumentor
    LangChainInstrumentor().uninstrument()

    base, scope, phx = base[warmup:], scope[warmup:], phx[warmup:]

    def report(name, xs, ref):
        over = [(x - b) / b * 100.0 for x, b in zip(xs, ref)]
        return (f"{name:<10} mean={statistics.mean(xs)*1000:8.2f}ms  "
                f"overhead-vs-baseline mean={statistics.mean(over):+7.2f}%  median={statistics.median(over):+7.2f}%")

    print(f"\n--- {label} (n={runs} per arm) ---")
    print(f"{'baseline':<10} mean={statistics.mean(base)*1000:8.2f}ms")
    print(report("agentscope", scope, base))
    print(report("phoenix", phx, base))


async def main(runs):
    print("Comparative overhead baseline: AgentScope vs Arize Phoenix (same workload)")
    await run_config("demo branching graph as-is", runs, warmup=3, node_delay_s=0.0)
    await run_config("branching graph, 100ms simulated LLM latency/node", runs, warmup=3, node_delay_s=0.1)
    await asyncio.sleep(3.0)  # let exporters flush


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=15)
    asyncio.run(main(p.parse_args().runs))
