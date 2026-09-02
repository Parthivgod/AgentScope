import functools
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from agentscope.context import get_execution_context
from agentscope.schema import Span, SpanStatus
from agentscope.sender import sender

logger = logging.getLogger(__name__)

def _extract_token_usage(response: Any) -> Optional[Dict[str, int]]:
    """
    Extracts token usage counts from OpenAI and Anthropic completion responses fail-silently.
    Handles prompt/completion (OpenAI) and input/output (Anthropic) token attributes.
    """
    def _to_int(val: Any) -> int:
        if isinstance(val, bool):
            return 0
        if isinstance(val, (int, float)):
            return int(val)
        if isinstance(val, str) and val.strip().isdigit():
            return int(val.strip())
        return 0

    try:
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            prompt_raw = getattr(usage, "prompt_tokens", None)
            if prompt_raw is None:
                prompt_raw = getattr(usage, "input_tokens", 0)

            comp_raw = getattr(usage, "completion_tokens", None)
            if comp_raw is None:
                comp_raw = getattr(usage, "output_tokens", 0)

            prompt_tokens = _to_int(prompt_raw)
            completion_tokens = _to_int(comp_raw)

            total_tokens_raw = getattr(usage, "total_tokens", None)
            total_tokens = _to_int(total_tokens_raw) if total_tokens_raw is not None else (prompt_tokens + completion_tokens)

            return {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }
        elif isinstance(response, dict) and "usage" in response:
            usage = response["usage"]
            if isinstance(usage, dict):
                prompt_tokens = _to_int(usage.get("prompt_tokens") if usage.get("prompt_tokens") is not None else usage.get("input_tokens", 0))
                completion_tokens = _to_int(usage.get("completion_tokens") if usage.get("completion_tokens") is not None else usage.get("output_tokens", 0))
                total_tokens_raw = usage.get("total_tokens", None)
                total_tokens = _to_int(total_tokens_raw) if total_tokens_raw is not None else (prompt_tokens + completion_tokens)

                return {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
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

def _patch_openai(agent_id: str = "openai-agent", trace_id: str = "default-trace") -> None:
    try:
        import openai
        from openai.resources.chat.completions import Completions, AsyncCompletions
    except ImportError:
        logger.warning("AgentScope: OpenAI module not installed, skipping OpenAI patch.")
        return

    # Sync patch
    if not getattr(Completions.create, "_agentscope_patched", False):
        original_sync_create = Completions.create

        @functools.wraps(original_sync_create)
        def sync_wrapper(self, *args, **kwargs):
            start_time = datetime.now(timezone.utc)
            span_id = str(uuid.uuid4())
            execution_context = get_execution_context(agent_id, trace_id)
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
                        trace_id=execution_context.trace_id,
                        span_id=span_id,
                        parent_span_id=execution_context.parent_span_id,
                        span_type="llm_call",
                        name=f"openai.{model_name}",
                        input=input_data,
                        output=output,
                        start_time=start_time,
                        end_time=end_time,
                        status=status,
                        token_usage=token_usage,
                        agent_id=execution_context.agent_id,
                        delegation_chain=list(execution_context.delegation_chain),
                        hop_number=execution_context.hop_number,
                    )
                    sender.send(span)
                except Exception as ex:
                    # Fail-silent guarantee (RULES.md §3.1, §3.2)
                    logger.warning(f"AgentScope OpenAI sync patch failed to record span: {ex}")

        sync_wrapper._agentscope_patched = True
        Completions.create = sync_wrapper

    # Async patch
    if not getattr(AsyncCompletions.create, "_agentscope_patched", False):
        original_async_create = AsyncCompletions.create

        @functools.wraps(original_async_create)
        async def async_wrapper(self, *args, **kwargs):
            start_time = datetime.now(timezone.utc)
            span_id = str(uuid.uuid4())
            execution_context = get_execution_context(agent_id, trace_id)
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
                        trace_id=execution_context.trace_id,
                        span_id=span_id,
                        parent_span_id=execution_context.parent_span_id,
                        span_type="llm_call",
                        name=f"openai.{model_name}",
                        input=input_data,
                        output=output,
                        start_time=start_time,
                        end_time=end_time,
                        status=status,
                        token_usage=token_usage,
                        agent_id=execution_context.agent_id,
                        delegation_chain=list(execution_context.delegation_chain),
                        hop_number=execution_context.hop_number,
                    )
                    sender.send(span)
                except Exception as ex:
                    logger.warning(f"AgentScope OpenAI async patch failed to record span: {ex}")

        async_wrapper._agentscope_patched = True
        AsyncCompletions.create = async_wrapper

def _patch_anthropic(agent_id: str = "anthropic-agent", trace_id: str = "default-trace") -> None:
    try:
        import anthropic
        from anthropic.resources.messages import Messages, AsyncMessages
    except ImportError:
        logger.warning("AgentScope: Anthropic module not installed, skipping Anthropic patch.")
        return

    # Sync patch
    if not getattr(Messages.create, "_agentscope_patched", False):
        original_sync_create = Messages.create

        @functools.wraps(original_sync_create)
        def sync_wrapper(self, *args, **kwargs):
            start_time = datetime.now(timezone.utc)
            span_id = str(uuid.uuid4())
            execution_context = get_execution_context(agent_id, trace_id)
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
                    model_name = kwargs.get("model", "claude-chat")
                    token_usage = _extract_token_usage(response) if response else None

                    input_data = {
                        "messages": kwargs.get("messages"),
                        "model": model_name,
                        "max_tokens": kwargs.get("max_tokens"),
                        "temperature": kwargs.get("temperature")
                    }

                    span = Span(
                        trace_id=execution_context.trace_id,
                        span_id=span_id,
                        parent_span_id=execution_context.parent_span_id,
                        span_type="llm_call",
                        name=f"anthropic.{model_name}",
                        input=input_data,
                        output=output,
                        start_time=start_time,
                        end_time=end_time,
                        status=status,
                        token_usage=token_usage,
                        agent_id=execution_context.agent_id,
                        delegation_chain=list(execution_context.delegation_chain),
                        hop_number=execution_context.hop_number,
                    )
                    sender.send(span)
                except Exception as ex:
                    logger.warning(f"AgentScope Anthropic sync patch failed to record span: {ex}")

        sync_wrapper._agentscope_patched = True
        Messages.create = sync_wrapper

    # Async patch
    if not getattr(AsyncMessages.create, "_agentscope_patched", False):
        original_async_create = AsyncMessages.create

        @functools.wraps(original_async_create)
        async def async_wrapper(self, *args, **kwargs):
            start_time = datetime.now(timezone.utc)
            span_id = str(uuid.uuid4())
            execution_context = get_execution_context(agent_id, trace_id)
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
                    model_name = kwargs.get("model", "claude-chat")
                    token_usage = _extract_token_usage(response) if response else None

                    input_data = {
                        "messages": kwargs.get("messages"),
                        "model": model_name,
                        "max_tokens": kwargs.get("max_tokens"),
                        "temperature": kwargs.get("temperature")
                    }

                    span = Span(
                        trace_id=execution_context.trace_id,
                        span_id=span_id,
                        parent_span_id=execution_context.parent_span_id,
                        span_type="llm_call",
                        name=f"anthropic.{model_name}",
                        input=input_data,
                        output=output,
                        start_time=start_time,
                        end_time=end_time,
                        status=status,
                        token_usage=token_usage,
                        agent_id=execution_context.agent_id,
                        delegation_chain=list(execution_context.delegation_chain),
                        hop_number=execution_context.hop_number,
                    )
                    sender.send(span)
                except Exception as ex:
                    logger.warning(f"AgentScope Anthropic async patch failed to record span: {ex}")

        async_wrapper._agentscope_patched = True
        AsyncMessages.create = async_wrapper

def patch(target_module: Any = None, agent_id: str = "llm-agent", trace_id: str = "default-trace") -> None:
    """
    Patches LLM client library calls (sync and async) to automatically capture LLM spans (Flow 2 integration).

    Monkey-patches target client methods (OpenAI's `Completions.create`/`AsyncCompletions.create` and
    Anthropic's `Messages.create`/`AsyncMessages.create`) to emit schema-compliant `llm_call` spans.
    Fails silently per RULES.md invariants #1 and #2 if target modules are missing or calls fail.

    Args:
        target_module: Target module or library name ("openai", "anthropic", or None to patch all supported).
        agent_id: Default agent identifier assigned to captured LLM spans.
        trace_id: Default trace identifier assigned to captured LLM spans.
    """
    targets = []
    if target_module is None or target_module == "all":
        targets = ["openai", "anthropic"]
    elif isinstance(target_module, str):
        targets = [target_module.lower()]
    elif hasattr(target_module, "__name__"):
        mod_name = target_module.__name__.lower()
        if "openai" in mod_name:
            targets = ["openai"]
        elif "anthropic" in mod_name:
            targets = ["anthropic"]
        else:
            targets = [mod_name]
    else:
        targets = ["openai", "anthropic"]

    if "openai" in targets:
        _patch_openai(agent_id=agent_id, trace_id=trace_id)
    if "anthropic" in targets:
        _patch_anthropic(agent_id=agent_id, trace_id=trace_id)

