import functools
import uuid
from datetime import datetime, timezone
import inspect
from agentscope.schema import Span, SpanStatus
from agentscope.sender import sender

def trace(name: str, span_type: str = "tool_call", agent_id: str = "custom-agent"):
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = datetime.now(timezone.utc)
                span_id = str(uuid.uuid4())
                trace_id = "custom-trace-1"
                status = SpanStatus(status="success")
                output = None
                
                try:
                    output = await func(*args, **kwargs)
                    return output
                except Exception as e:
                    status = SpanStatus(status="error", exception_details=str(e))
                    raise e
                finally:
                    end_time = datetime.now(timezone.utc)
                    span = Span(
                        trace_id=trace_id,
                        span_id=span_id,
                        span_type=span_type,
                        name=name,
                        input={"args": args, "kwargs": kwargs},
                        output=output,
                        start_time=start_time,
                        end_time=end_time,
                        status=status,
                        agent_id=agent_id
                    )
                    sender.send(span)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = datetime.now(timezone.utc)
                span_id = str(uuid.uuid4())
                trace_id = "custom-trace-1"
                status = SpanStatus(status="success")
                output = None
                
                try:
                    output = func(*args, **kwargs)
                    return output
                except Exception as e:
                    status = SpanStatus(status="error", exception_details=str(e))
                    raise e
                finally:
                    end_time = datetime.now(timezone.utc)
                    span = Span(
                        trace_id=trace_id,
                        span_id=span_id,
                        span_type=span_type,
                        name=name,
                        input={"args": args, "kwargs": kwargs},
                        output=output,
                        start_time=start_time,
                        end_time=end_time,
                        status=status,
                        agent_id=agent_id
                    )
                    sender.send(span)
            return sync_wrapper
    return decorator
