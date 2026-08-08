import pytest
import asyncio
from httpx import AsyncClient
from agentscope.sender import AsyncEventSender
from agentscope.schema import Span
from datetime import datetime, timezone

@pytest.fixture
def test_sender():
    sender = AsyncEventSender()
    yield sender
    # We should normally close the client but httpx warns if loop is closed early, ok for test

@pytest.mark.asyncio
async def test_fail_silent_backend_down(monkeypatch, test_sender):
    async def mock_post(*args, **kwargs):
        raise Exception("Backend is down")
    
    monkeypatch.setattr(test_sender.client, "post", mock_post)
    
    span = Span(
        trace_id="t1", span_id="s1", span_type="llm_call", name="test", 
        start_time=datetime.now(timezone.utc), agent_id="a1"
    )
    
    test_sender.send(span)
    
    await asyncio.sleep(0.1) # Yield control
    assert test_sender.queue.empty()

@pytest.mark.asyncio
async def test_fail_silent_invalid_key(monkeypatch, test_sender):
    class MockResponse:
        status_code = 401
        def raise_for_status(self):
            raise Exception("401 Unauthorized")
            
    async def mock_post(*args, **kwargs):
        return MockResponse()
    
    monkeypatch.setattr(test_sender.client, "post", mock_post)
    
    span = Span(
        trace_id="t1", span_id="s1", span_type="llm_call", name="test", 
        start_time=datetime.now(timezone.utc), agent_id="a1"
    )
    
    test_sender.send(span)
    
    await asyncio.sleep(0.1)
    assert test_sender.queue.empty()

@pytest.mark.asyncio
async def test_fail_silent_timeout(monkeypatch, test_sender):
    async def mock_post(*args, **kwargs):
        await asyncio.sleep(1.0)
        raise asyncio.TimeoutError()
        
    monkeypatch.setattr(test_sender.client, "post", mock_post)
    
    span = Span(
        trace_id="t1", span_id="s1", span_type="llm_call", name="test", 
        start_time=datetime.now(timezone.utc), agent_id="a1"
    )
    
    test_sender.send(span)
    await asyncio.sleep(0.1)
    # The worker handles timeout and doesn't crash the host
    # It might still be processing, but the send() call returned instantly
