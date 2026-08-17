import pytest
import asyncio
import httpx
from datetime import datetime, timezone
from agentscope.sender import AsyncEventSender
from agentscope.schema import Span

@pytest.fixture
def test_sender():
    sender = AsyncEventSender(max_retries=2, initial_backoff=0.01, backoff_factor=2.0)
    yield sender

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
    await asyncio.sleep(0.1)
    assert test_sender.queue.empty()

@pytest.mark.asyncio
async def test_no_retry_on_401_client_error(monkeypatch, test_sender):
    call_count = 0

    class MockResponse:
        status_code = 401

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return MockResponse()
    
    monkeypatch.setattr(test_sender.client, "post", mock_post)
    
    span = Span(
        trace_id="t1", span_id="s1", span_type="llm_call", name="test", 
        start_time=datetime.now(timezone.utc), agent_id="a1"
    )
    
    test_sender.send(span)
    await asyncio.sleep(0.1)
    
    # 401 is a non-transient client error, so it must not retry
    assert call_count == 1
    assert test_sender.queue.empty()

@pytest.mark.asyncio
async def test_retry_on_transient_500_error(monkeypatch, test_sender):
    call_count = 0

    class MockResponse:
        status_code = 500
        def raise_for_status(self):
            raise httpx.HTTPStatusError("500 Server Error", request=None, response=self)

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return MockResponse()

    monkeypatch.setattr(test_sender.client, "post", mock_post)

    span = Span(
        trace_id="t1", span_id="s1", span_type="llm_call", name="test", 
        start_time=datetime.now(timezone.utc), agent_id="a1"
    )

    test_sender.send(span)
    await asyncio.sleep(0.1)

    # max_retries = 2 -> initial call + 2 retries = 3 attempts total
    assert call_count == 3
    assert test_sender.queue.empty()

@pytest.mark.asyncio
async def test_retry_eventually_succeeds(monkeypatch, test_sender):
    call_count = 0

    class MockErrorResponse:
        status_code = 503
        def raise_for_status(self):
            raise httpx.HTTPStatusError("503 Service Unavailable", request=None, response=self)

    class MockSuccessResponse:
        status_code = 200
        def raise_for_status(self): pass

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockErrorResponse()
        return MockSuccessResponse()

    monkeypatch.setattr(test_sender.client, "post", mock_post)

    span = Span(
        trace_id="t1", span_id="s1", span_type="llm_call", name="test", 
        start_time=datetime.now(timezone.utc), agent_id="a1"
    )

    test_sender.send(span)
    await asyncio.sleep(0.1)

    # Succeeded on 2nd call
    assert call_count == 2
    assert test_sender.queue.empty()

@pytest.mark.asyncio
async def test_sender_handles_malformed_token_usage_span(monkeypatch, test_sender):
    from agentscope.schema import TokenUsage

    posted_payload = None

    class MockResponse:
        status_code = 200
        def raise_for_status(self): pass

    async def mock_post(*args, **kwargs):
        nonlocal posted_payload
        posted_payload = kwargs.get("json")
        return MockResponse()

    monkeypatch.setattr(test_sender.client, "post", mock_post)

    # TokenUsage with None or missing counters
    span = Span(
        trace_id="t_malformed",
        span_id="s_malformed",
        span_type="llm_call",
        name="test_llm",
        start_time=datetime.now(timezone.utc),
        token_usage=TokenUsage(prompt_tokens=None, completion_tokens=None, total_tokens=None),
        agent_id="a1"
    )

    test_sender.send(span)
    await asyncio.sleep(0.1)

    assert posted_payload is not None
    assert posted_payload["token_usage"] == {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    assert test_sender.queue.empty()

