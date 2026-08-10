import functools
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from agentscope.schema import Span, SpanStatus
from agentscope.sender import sender

logger = logging.getLogger(__name__)

def _extract_token_usage(response: Any) -> Optional[Dict[str, int]]:
    try:
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            total_tokens = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
            return {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }
        elif isinstance(response, dict) and "usage" in response:
            usage = response["usage"]
            if isinstance(usage, dict):
                prompt = usage.get("prompt_tokens", 0) or 0
                comp = usage.get("completion_tokens", 0) or 0
                tot = usage.get("total_tokens", 0) or (prompt + comp)
                return {
                    "prompt_tokens": prompt,
                    "completion_tokens": comp,
                    "total_tokens": tot
                }
    except Exception as e:
        logger.warning(f"AgentScope failed to extract token usage: {e}")
    return None

def _extract_output(response: Any) -> Any:
    try:
        if hasattr(response, "model_dump") and callable(response.model_dump):
            return response.model_dump(mode="json")
        elif isinstance(response, dict):
            return response
        else:
            return str(response)
    except Exception:
        return str(response)

def patch(target_module: Any = None, agent_id: str = "openai-agent", trace_id: str = "default-trace") -> None:
    """
    Patches OpenAI client calls (sync and async) to automatically capture LLM spans.
    Locked decision: OpenAI is the first/target LLM client (RULES.md §2 Decision 6).
    """
    try:
        import openai
        from openai.resources.chat.completions import Completions, AsyncCompletions
    except ImportError:
        logger.warning("AgentScope: OpenAI module not installed, skipping patch.")
        return

    # Sync patch
    if not getattr(Completions.create, "_agentscope_patched", False):
        original_sync_create = Completions.create

        @functools.wraps(original_sync_create)
        def sync_wrapper(self, *args, **kwargs):
            start_time = datetime.now(timezone.utc)
            span_id = str(uuid.uuid4())
            status = SpanStatus(status="success")
            output = None
            response = None

            try:
                response = original_sync_create(self, *args, **kwargs)
                output = _extract_output(response)
                return response
            except Exception as e:
                status = SpanStatus(status="error", exception_details=str(e))
                raise
            finally:
                try:
                    end_time = datetime.now(timezone.utc)
                    model_name = kwargs.get("model", "openai-chat")
                    token_usage = _extract_token_usage(response) if response else None

                    input_data = {
                        "messages": kwargs.get("messages"),
                        "model": model_name,
                        "temperature": kwargs.get("temperature")
                    }

                    span = Span(
                        trace_id=trace_id,
                        span_id=span_id,
                        span_type="llm_call",
                        name=f"openai.{model_name}",
                        input=input_data,
                        output=output,
                        start_time=start_time,
                        end_time=end_time,
                        status=status,
                        token_usage=token_usage,
                        agent_id=agent_id
                    )
                    sender.send(span)
                except Exception as ex:
                    # Fail-silent guarantee (RULES.md §3.1, §3.2)
                    logger.warning(f"AgentScope patch failed to record span: {ex}")

        sync_wrapper._agentscope_patched = True
        Completions.create = sync_wrapper

    # Async patch
    if not getattr(AsyncCompletions.create, "_agentscope_patched", False):
        original_async_create = AsyncCompletions.create

        @functools.wraps(original_async_create)
        async def async_wrapper(self, *args, **kwargs):
            start_time = datetime.now(timezone.utc)
            span_id = str(uuid.uuid4())
            status = SpanStatus(status="success")
            output = None
            response = None

            try:
                response = await original_async_create(self, *args, **kwargs)
                output = _extract_output(response)
                return response
            except Exception as e:
                status = SpanStatus(status="error", exception_details=str(e))
                raise
            finally:
                try:
                    end_time = datetime.now(timezone.utc)
                    model_name = kwargs.get("model", "openai-chat")
                    token_usage = _extract_token_usage(response) if response else None

                    input_data = {
                        "messages": kwargs.get("messages"),
                        "model": model_name,
                        "temperature": kwargs.get("temperature")
                    }

                    span = Span(
                        trace_id=trace_id,
                        span_id=span_id,
                        span_type="llm_call",
                        name=f"openai.{model_name}",
                        input=input_data,
                        output=output,
                        start_time=start_time,
                        end_time=end_time,
                        status=status,
                        token_usage=token_usage,
                        agent_id=agent_id
                    )
                    sender.send(span)
                except Exception as ex:
                    logger.warning(f"AgentScope async patch failed to record span: {ex}")

        async_wrapper._agentscope_patched = True
        AsyncCompletions.create = async_wrapper
