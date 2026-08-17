import pytest
import asyncio
from unittest.mock import MagicMock
from datetime import datetime, timezone
import openai
from openai.resources.chat.completions import Completions, AsyncCompletions

from agentscope.patch import patch
from agentscope.sender import sender
from agentscope.schema import Span, SpanStatus

@pytest.fixture(autouse=True)
def clear_sender_queue():
    while not sender.queue.empty():
        sender.queue.get_nowait()
    yield
    while not sender.queue.empty():
        sender.queue.get_nowait()

def test_sync_openai_patch_success():
    mock_response = MagicMock()
    mock_response.usage.prompt_tokens = 20
    mock_response.usage.completion_tokens = 10
    mock_response.usage.total_tokens = 30
    mock_response.model_dump.return_value = {"id": "chatcmpl-sync", "choices": [{"message": {"content": "Hello world"}}]}

    mock_client = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        def dummy_sync_create(self, *args, **kwargs):
            return mock_response
            
        m.setattr("openai.resources.chat.completions.Completions.create", dummy_sync_create)
        if hasattr(Completions.create, "_agentscope_patched"):
            delattr(Completions.create, "_agentscope_patched")

        patch(agent_id="sync-agent", trace_id="sync-trace-123")
        
        completions_inst = Completions(client=mock_client)
        res = completions_inst.create(model="gpt-4o", messages=[{"role": "user", "content": "Hi"}])

    assert res == mock_response
    span: Span = sender.queue.get_nowait()
    assert span.span_type == "llm_call"
    assert span.name == "openai.gpt-4o"
    assert span.agent_id == "sync-agent"
    assert span.trace_id == "sync-trace-123"
    assert span.status.status == "success"
    assert span.token_usage.prompt_tokens == 20
    assert span.token_usage.completion_tokens == 10
    assert span.token_usage.total_tokens == 30

def test_sync_openai_patch_error_handling():
    mock_client = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        def dummy_failing_create(self, *args, **kwargs):
            raise ValueError("OpenAI Rate Limit Exceeded")
            
        m.setattr("openai.resources.chat.completions.Completions.create", dummy_failing_create)
        if hasattr(Completions.create, "_agentscope_patched"):
            delattr(Completions.create, "_agentscope_patched")

        patch(agent_id="sync-agent-err", trace_id="sync-trace-err")
        
        completions_inst = Completions(client=mock_client)
        with pytest.raises(ValueError, match="OpenAI Rate Limit Exceeded"):
            completions_inst.create(model="gpt-4o", messages=[{"role": "user", "content": "Hi"}])

    span: Span = sender.queue.get_nowait()
    assert span.span_type == "llm_call"
    assert span.status.status == "error"
    assert "OpenAI Rate Limit Exceeded" in span.status.exception_details

@pytest.mark.asyncio
async def test_async_openai_patch_success():
    mock_response = MagicMock()
    mock_response.usage.prompt_tokens = 15
    mock_response.usage.completion_tokens = 5
    mock_response.usage.total_tokens = 20
    mock_response.model_dump.return_value = {"id": "chatcmpl-async", "choices": [{"message": {"content": "Async Hello"}}]}

    mock_client = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        async def dummy_async_create(self, *args, **kwargs):
            return mock_response
            
        m.setattr("openai.resources.chat.completions.AsyncCompletions.create", dummy_async_create)
        if hasattr(AsyncCompletions.create, "_agentscope_patched"):
            delattr(AsyncCompletions.create, "_agentscope_patched")

        patch(agent_id="async-agent", trace_id="async-trace-123")
        
        async_completions_inst = AsyncCompletions(client=mock_client)
        res = await async_completions_inst.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Async Hi"}])

    assert res == mock_response
    span: Span = sender.queue.get_nowait()
    assert span.span_type == "llm_call"
    assert span.name == "openai.gpt-4o-mini"
    assert span.agent_id == "async-agent"
    assert span.trace_id == "async-trace-123"
    assert span.status.status == "success"
    assert span.token_usage.prompt_tokens == 15
    assert span.token_usage.completion_tokens == 5

def test_extract_token_usage_malformed_attribute():
    from agentscope.patch import _extract_token_usage

    class BadUsage:
        @property
        def prompt_tokens(self):
            raise ValueError("Corrupted attribute")

    class ResponseWithBadUsage:
        usage = BadUsage()

    # Must fail silent and return None, not raise exception
    usage = _extract_token_usage(ResponseWithBadUsage())
    assert usage is None

def test_extract_token_usage_string_and_dict_variants():
    from agentscope.patch import _extract_token_usage

    class StringUsage:
        prompt_tokens = "100"
        completion_tokens = "50"
        total_tokens = "150"

    class ResponseWithStringUsage:
        usage = StringUsage()

    usage = _extract_token_usage(ResponseWithStringUsage())
    assert usage == {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    # Dict response with invalid non-int token counts
    dict_response = {"usage": {"prompt_tokens": "invalid", "completion_tokens": None, "total_tokens": []}}
    usage_dict = _extract_token_usage(dict_response)
    assert usage_dict == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

def test_extract_token_usage_anthropic_format():
    from agentscope.patch import _extract_token_usage

    class AnthropicUsage:
        input_tokens = 60
        output_tokens = 30

    class AnthropicResponse:
        usage = AnthropicUsage()

    usage = _extract_token_usage(AnthropicResponse())
    assert usage == {"prompt_tokens": 60, "completion_tokens": 30, "total_tokens": 90}

def test_sync_anthropic_patch_success():
    from types import ModuleType
    import sys

    class AnthropicUsage:
        input_tokens = 40
        output_tokens = 25

    mock_response = MagicMock()
    mock_response.usage = AnthropicUsage()
    mock_response.model_dump.return_value = {"id": "msg-sync", "content": [{"type": "text", "text": "Claude response"}]}

    mock_anthropic = ModuleType("anthropic")
    mock_messages_mod = ModuleType("anthropic.resources.messages")

    class DummyMessages:
        def create(self, *args, **kwargs):
            return mock_response

    class DummyAsyncMessages:
        async def create(self, *args, **kwargs):
            return mock_response

    mock_messages_mod.Messages = DummyMessages
    mock_messages_mod.AsyncMessages = DummyAsyncMessages
    mock_anthropic.resources = ModuleType("anthropic.resources")
    mock_anthropic.resources.messages = mock_messages_mod

    with pytest.MonkeyPatch.context() as m:
        m.setitem(sys.modules, "anthropic", mock_anthropic)
        m.setitem(sys.modules, "anthropic.resources.messages", mock_messages_mod)

        patch(target_module="anthropic", agent_id="claude-agent", trace_id="anthropic-trace-123")

        msg_inst = DummyMessages()
        res = msg_inst.create(model="claude-3-5-sonnet", messages=[{"role": "user", "content": "Hello Claude"}])

    assert res == mock_response
    span: Span = sender.queue.get_nowait()
    assert span.span_type == "llm_call"
    assert span.name == "anthropic.claude-3-5-sonnet"
    assert span.agent_id == "claude-agent"
    assert span.trace_id == "anthropic-trace-123"
    assert span.status.status == "success"
    assert span.token_usage.prompt_tokens == 40
    assert span.token_usage.completion_tokens == 25
    assert span.token_usage.total_tokens == 65

@pytest.mark.asyncio
async def test_async_anthropic_patch_success():
    from types import ModuleType
    import sys

    class AnthropicUsage:
        input_tokens = 30
        output_tokens = 15

    mock_response = MagicMock()
    mock_response.usage = AnthropicUsage()
    mock_response.model_dump.return_value = {"id": "msg-async", "content": [{"type": "text", "text": "Async Claude"}]}

    mock_anthropic = ModuleType("anthropic")
    mock_messages_mod = ModuleType("anthropic.resources.messages")

    class DummyMessages:
        def create(self, *args, **kwargs): return mock_response

    class DummyAsyncMessages:
        async def create(self, *args, **kwargs): return mock_response

    mock_messages_mod.Messages = DummyMessages
    mock_messages_mod.AsyncMessages = DummyAsyncMessages
    mock_anthropic.resources = ModuleType("anthropic.resources")
    mock_anthropic.resources.messages = mock_messages_mod

    with pytest.MonkeyPatch.context() as m:
        m.setitem(sys.modules, "anthropic", mock_anthropic)
        m.setitem(sys.modules, "anthropic.resources.messages", mock_messages_mod)

        patch(target_module="anthropic", agent_id="async-claude-agent", trace_id="async-anthropic-trace")

        async_msg_inst = DummyAsyncMessages()
        res = await async_msg_inst.create(model="claude-3-haiku", messages=[{"role": "user", "content": "Async Claude"}])

    assert res == mock_response
    span: Span = sender.queue.get_nowait()
    assert span.span_type == "llm_call"
    assert span.name == "anthropic.claude-3-haiku"
    assert span.agent_id == "async-claude-agent"
    assert span.trace_id == "async-anthropic-trace"
    assert span.status.status == "success"
    assert span.token_usage.prompt_tokens == 30
    assert span.token_usage.completion_tokens == 15
    assert span.token_usage.total_tokens == 45

def test_extract_token_usage_non_numeric_and_unexpected_types():
    from agentscope.patch import _extract_token_usage

    class UnexpectedUsage:
        prompt_tokens = object()
        completion_tokens = "non-numeric"
        total_tokens = None

    class ResponseWithUnexpectedUsage:
        usage = UnexpectedUsage()

    usage = _extract_token_usage(ResponseWithUnexpectedUsage())
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}



