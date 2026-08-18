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
