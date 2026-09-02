import functools
import inspect
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from agentscope.context import (
    _current_agent_id,
    _current_delegation_chain,
    _current_span_id,
    _current_trace_id,
)
from agentscope.schema import Span, SpanStatus
from agentscope.sender import sender


def _resolve_context(
    name: str,
    span_type: str,
    declared_agent_id: Optional[str],
) -> Tuple[str, str, Optional[str], Tuple[str, ...], int]:
    parent_span_id = _current_span_id.get()
    trace_id = _current_trace_id.get() or f"trace-{uuid.uuid4()}"
    current_agent_id = _current_agent_id.get()
    current_chain = _current_delegation_chain.get()

    is_agent_boundary = span_type == "delegation"
    if declared_agent_id:
        effective_agent_id = declared_agent_id
    elif is_agent_boundary:
        effective_agent_id = name
    else:
        effective_agent_id = current_agent_id or "custom-agent"

    delegation_chain = current_chain
    if is_agent_boundary and (
        not delegation_chain or delegation_chain[-1] != effective_agent_id
    ):
        delegation_chain = (*delegation_chain, effective_agent_id)

    hop_number = max(len(delegation_chain) - 1, 0)
    return (
        trace_id,
        effective_agent_id,
        parent_span_id,
        delegation_chain,
        hop_number,
    )


def _make_span(
    *,
    trace_id: str,
    span_id: str,
    parent_span_id: Optional[str],
    span_type: str,
    name: str,
    input_data,
    output,
    start_time: datetime,
    end_time: Optional[datetime],
    status: SpanStatus,
    agent_id: str,
    delegation_chain: Tuple[str, ...],
    hop_number: int,
) -> Span:
    return Span(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        span_type=span_type,
        name=name,
        input=input_data,
        output=output,
        start_time=start_time,
        end_time=end_time,
        status=status,
        agent_id=agent_id,
        delegation_chain=list(delegation_chain),
        hop_number=hop_number,
    )


def trace(
    name: str,
    span_type: str = "tool_call",
    agent_id: Optional[str] = None,
):
    """
    Decorate a custom Python operation and propagate execution context.

    A ``delegation`` span is an agent boundary. It appends its agent identity
    (or ``name`` when no identity is supplied) to the delegation chain. All
    nested decorated calls and patched LLM clients inherit trace/span context
    through ``contextvars`` without function-argument plumbing.
    """

    def decorator(func):
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = datetime.now(timezone.utc)
                span_id = str(uuid.uuid4())
                (
                    trace_id,
                    effective_agent_id,
                    parent_span_id,
                    delegation_chain,
                    hop_number,
                ) = _resolve_context(name, span_type, agent_id)
                input_data = {"args": args, "kwargs": kwargs}
                status = SpanStatus(status="success")

                sender.send(
                    _make_span(
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        span_type=span_type,
                        name=name,
                        input_data=input_data,
                        output=None,
                        start_time=start_time,
                        end_time=None,
                        status=status,
                        agent_id=effective_agent_id,
                        delegation_chain=delegation_chain,
                        hop_number=hop_number,
                    )
                )

                token_trace = _current_trace_id.set(trace_id)
                token_span = _current_span_id.set(span_id)
                token_agent = _current_agent_id.set(effective_agent_id)
                token_chain = _current_delegation_chain.set(delegation_chain)
                output = None

                try:
                    output = await func(*args, **kwargs)
                    return output
                except Exception as exc:
                    status = SpanStatus(status="error", exception_details=str(exc))
                    raise
                finally:
                    _current_delegation_chain.reset(token_chain)
                    _current_agent_id.reset(token_agent)
                    _current_span_id.reset(token_span)
                    _current_trace_id.reset(token_trace)
                    sender.send(
                        _make_span(
                            trace_id=trace_id,
                            span_id=span_id,
                            parent_span_id=parent_span_id,
                            span_type=span_type,
                            name=name,
                            input_data=input_data,
                            output=output,
                            start_time=start_time,
                            end_time=datetime.now(timezone.utc),
                            status=status,
                            agent_id=effective_agent_id,
                            delegation_chain=delegation_chain,
                            hop_number=hop_number,
                        )
                    )

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = datetime.now(timezone.utc)
            span_id = str(uuid.uuid4())
            (
                trace_id,
                effective_agent_id,
                parent_span_id,
                delegation_chain,
                hop_number,
            ) = _resolve_context(name, span_type, agent_id)
            input_data = {"args": args, "kwargs": kwargs}
            status = SpanStatus(status="success")

            sender.send(
                _make_span(
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    span_type=span_type,
                    name=name,
                    input_data=input_data,
                    output=None,
                    start_time=start_time,
                    end_time=None,
                    status=status,
                    agent_id=effective_agent_id,
                    delegation_chain=delegation_chain,
                    hop_number=hop_number,
                )
            )

            token_trace = _current_trace_id.set(trace_id)
            token_span = _current_span_id.set(span_id)
            token_agent = _current_agent_id.set(effective_agent_id)
            token_chain = _current_delegation_chain.set(delegation_chain)
            output = None

            try:
                output = func(*args, **kwargs)
                return output
            except Exception as exc:
                status = SpanStatus(status="error", exception_details=str(exc))
                raise
            finally:
                _current_delegation_chain.reset(token_chain)
                _current_agent_id.reset(token_agent)
                _current_span_id.reset(token_span)
                _current_trace_id.reset(token_trace)
                sender.send(
                    _make_span(
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        span_type=span_type,
                        name=name,
                        input_data=input_data,
                        output=output,
                        start_time=start_time,
                        end_time=datetime.now(timezone.utc),
                        status=status,
                        agent_id=effective_agent_id,
                        delegation_chain=delegation_chain,
                        hop_number=hop_number,
                    )
                )

        return sync_wrapper

    return decorator
