import pytest
from fastapi.testclient import TestClient
from agentscope.schema import Span
from app.ingest import app
from datetime import datetime, timezone
import os

client = TestClient(app)

@pytest.fixture(autouse=True)
def set_env():
    os.environ["AGENTSCOPE_API_KEY"] = "test-secret-key"
    yield
    del os.environ["AGENTSCOPE_API_KEY"]

def get_valid_span_payload():
    return {
        "trace_id": "trace-123",
        "span_id": "span-123",
        "parent_span_id": None,
        "span_type": "llm_call",
        "name": "gpt-4o",
        "input": {"prompt": "hello"},
        "output": {"response": "hi"},
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "status": {"status": "success", "exception_details": None},
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "agent_id": "agent-1"
    }

def test_ingest_missing_api_key():
    response = client.post("/ingest", json=get_valid_span_payload())
    assert response.status_code == 403 or response.status_code == 401 # FastAPI dependencies might raise 403 or we raise 401
    
    # Wait, our middleware explicitly raises HTTPException(status_code=401, detail="Invalid API Key") if key differs,
    # but if there is no Authorization header, request.headers.get("Authorization") is None. 
    # Let's see what the backend expects. In our app/ingest.py, if api_key != expected_key it raises 401.
    assert response.status_code == 401

def test_ingest_invalid_api_key():
    headers = {"Authorization": "Bearer wrong-key"}
    response = client.post("/ingest", json=get_valid_span_payload(), headers=headers)
    assert response.status_code == 401

def test_ingest_valid_api_key():
    headers = {"Authorization": "Bearer test-secret-key"}
    response = client.post("/ingest", json=get_valid_span_payload(), headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "span_id": "span-123"}

def test_ingest_invalid_payload():
    headers = {"Authorization": "Bearer test-secret-key"}
    invalid_payload = get_valid_span_payload()
    del invalid_payload["span_type"] # Missing required field
    response = client.post("/ingest", json=invalid_payload, headers=headers)
    assert response.status_code == 422 # Pydantic validation error


def test_backend_redis_client_has_bounded_reconnect_policy():
    """A recovered Redis must not leave the first request on a stale socket."""
    from app import redis_client

    redis_client._clients.clear()
    configured = redis_client.get_redis()
    connection = configured.connection_pool.make_connection()

    assert connection.health_check_interval == 1
    assert connection.retry._retries == 5
