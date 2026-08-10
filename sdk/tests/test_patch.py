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
