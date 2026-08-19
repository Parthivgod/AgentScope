"""
AgentScope SDK — Lightweight Observability & Telemetry for Multi-Agent Systems.

This package provides zero-rewrite and decorator-based instrumentation for tracking agent runs,
tool calls, LLM invocations, and state updates with live visualization and anomaly detection.

Integration Paths:
------------------
1. Flow 1: LangGraph Integration (Zero-Rewrite Callback Path)
   For agents built using LangGraph / LangChain, attach `LangGraphAdapter` to your graph's
   callback handlers without modifying any inner agent logic:

   >>> from agentscope import LangGraphAdapter
   >>> adapter = LangGraphAdapter(agent_id="my-langgraph-agent", trace_id="trace-123")
   >>> graph.invoke(input_data, config={"callbacks": [adapter]})

2. Flow 2: Custom / Decorator Integration Path
   For custom Python agents, use `@trace` decorator for functions/methods and `patch(openai)`
   to intercept LLM API calls:

   >>> import agentscope
   >>> agentscope.patch()  # Intercept OpenAI completion calls
   >>>
   >>> @agentscope.trace(name="search_tool", span_type="tool_call", agent_id="researcher")
   ... def search(query: str):
   ...     return "search results"

Public Entry Points:
-------------------
- LangGraphAdapter : Callback tracer for LangGraph / LangChain workflows (Flow 1).
- trace            : Decorator for custom functions / tool calls / agent nodes (Flow 2).
- patch            : Automatic monkey-patcher for LLM client libraries (Flow 2).
- Span             : Core telemetry Pydantic model for a single operation/event.
- Trace            : Aggregated Pydantic model representing a sequence of spans.
- TokenUsage       : Telemetry model for prompt, completion, and total token counters.
- SpanStatus       : Telemetry model for status ("success" | "error") and exception details.
"""

from agentscope.schema import Span, Trace, TokenUsage, SpanStatus

# Lazy imports for modules with optional heavy dependencies (langchain_core,
# openai, httpx).  The backend and worker containers only need schema.py and
# must not be forced to install the full SDK dependency tree.
def __getattr__(name: str):
    if name == "trace":
        from agentscope.trace import trace as _trace
        return _trace
    if name == "LangGraphAdapter":
        from agentscope.adapters.langgraph import LangGraphAdapter as _LGA
        return _LGA
    if name == "patch":
        from agentscope.patch import patch as _patch
        return _patch
    raise AttributeError(f"module 'agentscope' has no attribute {name!r}")

__all__ = [
    "Span",
    "Trace",
    "TokenUsage",
    "SpanStatus",
    "trace",
    "LangGraphAdapter",
    "patch",
]

