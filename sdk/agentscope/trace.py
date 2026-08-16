import functools
import uuid
from datetime import datetime, timezone
import inspect
import contextvars
from agentscope.schema import Span, SpanStatus
from agentscope.sender import sender

_current_trace_id = contextvars.ContextVar('current_trace_id', default=None)
_current_span_id = contextvars.ContextVar('current_span_id', default=None)

def trace(name: str, span_type: str = "tool_call", agent_id: str = "custom-agent"):
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = datetime.now(timezone.utc)
                span_id = str(uuid.uuid4())
                
                parent_span_id = _current_span_id.get()
                trace_id = _current_trace_id.get()
                if not trace_id:
                    trace_id = f"trace-{span_id}"
                
                status = SpanStatus(status="success")
                
                # Emit live 'active' span
                active_span = Span(
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    span_type=span_type,
                    name=name,
                    input={"args": args, "kwargs": kwargs},
                    output=None,
                    start_time=start_time,
                    end_time=None,
                    status=status,
                    agent_id=agent_id
                )
                sender.send(active_span)

                token_trace = _current_trace_id.set(trace_id)
                token_span = _current_span_id.set(span_id)
                output = None
                
                try:
                    output = await func(*args, **kwargs)
                    return output
                except Exception as e:
                    status = SpanStatus(status="error", exception_details=str(e))
                    raise e
                finally:
                    _current_trace_id.reset(token_trace)
                    _current_span_id.reset(token_span)
                    
                    end_time = datetime.now(timezone.utc)
                    complete_span = Span(
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        span_type=span_type,
                        name=name,
                        input={"args": args, "kwargs": kwargs},
                        output=output,
                        start_time=start_time,
                        end_time=end_time,
                        status=status,
                        agent_id=agent_id
                    )
                    sender.send(complete_span)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = datetime.now(timezone.utc)
                span_id = str(uuid.uuid4())
                
                parent_span_id = _current_span_id.get()
                trace_id = _current_trace_id.get()
                if not trace_id:
                    trace_id = f"trace-{span_id}"
                
                status = SpanStatus(status="success")
                
                # Emit live 'active' span
                active_span = Span(
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    span_type=span_type,
                    name=name,
                    input={"args": args, "kwargs": kwargs},
                    output=None,
                    start_time=start_time,
                    end_time=None,
                    status=status,
                    agent_id=agent_id
                )
                sender.send(active_span)

                token_trace = _current_trace_id.set(trace_id)
                token_span = _current_span_id.set(span_id)
                output = None
                
                try:
                    output = func(*args, **kwargs)
                    return output
                except Exception as e:
                    status = SpanStatus(status="error", exception_details=str(e))
                    raise e
                finally:
                    _current_trace_id.reset(token_trace)
                    _current_span_id.reset(token_span)

                    end_time = datetime.now(timezone.utc)
                    complete_span = Span(
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        span_type=span_type,
                        name=name,
                        input={"args": args, "kwargs": kwargs},
                        output=output,
                        start_time=start_time,
                        end_time=end_time,
                        status=status,
                        agent_id=agent_id
                    )
                    sender.send(complete_span)
            return sync_wrapper
    return decorator
