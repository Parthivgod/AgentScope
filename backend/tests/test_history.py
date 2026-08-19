import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
import os

from app.ingest import app
from app.redis_client import redis_client

client = TestClient(app)

@pytest.fixture(autouse=True)
def set_env():
    os.environ["AGENTSCOPE_API_KEY"] = "test-secret-key"
    yield
    if "AGENTSCOPE_API_KEY" in os.environ:
        del os.environ["AGENTSCOPE_API_KEY"]

import asyncio

@pytest.fixture(autouse=True)
def clear_redis():
    asyncio.run(redis_client.delete("agentscope:events"))
    yield
    asyncio.run(redis_client.delete("agentscope:events"))

def get_valid_span_payload(span_id):
    return {
        "trace_id": "history-trace-1",
        "span_id": span_id,
        "parent_span_id": None,
        "span_type": "llm_call",
        "name": "gpt-4",
        "input": {"prompt": "hello"},
        "output": {"response": "hi"},
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "status": {"status": "success", "exception_details": None},
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "agent_id": "agent-1"
    }

def test_history_endpoint():
    headers = {"Authorization": "Bearer test-secret-key"}
    
    # Ingest spans for history-trace-1
    span1 = get_valid_span_payload("s1")
    span2 = get_valid_span_payload("s2")
    client.post("/ingest", json=span1, headers=headers)
    client.post("/ingest", json=span2, headers=headers)
    
    # Ingest span for a different trace
    span_other = get_valid_span_payload("s3")
    span_other["trace_id"] = "history-trace-2"
    client.post("/ingest", json=span_other, headers=headers)
    
    # Query history endpoint
    response = client.get("/history/history-trace-1")
    assert response.status_code == 200
    
    trace_data = response.json()
    assert trace_data["trace_id"] == "history-trace-1"
    
    spans = trace_data["spans"]
    assert len(spans) == 2
    
    # Check strict arrival order
    assert spans[0]["span_id"] == "s1"
    assert spans[1]["span_id"] == "s2"
    
def test_history_not_found():
    response = client.get("/history/unknown-trace")
    assert response.status_code == 404
