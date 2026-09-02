"""Execution-scoped context shared by custom decorators and LLM patches."""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional, Tuple


_current_trace_id: ContextVar[Optional[str]] = ContextVar("agentscope_trace_id", default=None)
_current_span_id: ContextVar[Optional[str]] = ContextVar("agentscope_span_id", default=None)
_current_agent_id: ContextVar[Optional[str]] = ContextVar("agentscope_agent_id", default=None)
_current_delegation_chain: ContextVar[Tuple[str, ...]] = ContextVar(
    "agentscope_delegation_chain", default=()
)


@dataclass(frozen=True)
class ExecutionContext:
    trace_id: str
    parent_span_id: Optional[str]
    agent_id: str
    delegation_chain: Tuple[str, ...]
    hop_number: int


def get_execution_context(default_agent_id: str, default_trace_id: str) -> ExecutionContext:
    """Return the active custom-agent context, falling back to patch defaults."""
    chain = _current_delegation_chain.get()
    return ExecutionContext(
        trace_id=_current_trace_id.get() or default_trace_id,
        parent_span_id=_current_span_id.get(),
        agent_id=_current_agent_id.get() or default_agent_id,
        delegation_chain=chain,
        hop_number=max(len(chain) - 1, 0),
    )
