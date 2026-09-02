import json
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
import os
from concurrent.futures import ThreadPoolExecutor

from app.ingest import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def set_env():
    os.environ["AGENTSCOPE_API_KEY"] = "test-secret-key"
    yield
    if "AGENTSCOPE_API_KEY" in os.environ:
        del os.environ["AGENTSCOPE_API_KEY"]

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

def test_traces_lists_distinct_trace_ids_most_recent_first():
    headers = {"Authorization": "Bearer test-secret-key"}

    for trace_id, span_id in [("tr-a", "a1"), ("tr-b", "b1"), ("tr-a", "a2")]:
        payload = get_valid_span_payload(span_id)
        payload["trace_id"] = trace_id
        client.post("/ingest", json=payload, headers=headers)

    response = client.get("/traces")
    assert response.status_code == 200
    trace_ids = response.json()["trace_ids"]
    assert set(trace_ids) == {"tr-a", "tr-b"}
    # tr-a has the most recent event, so it must be listed first
    assert trace_ids[0] == "tr-a"

def test_traces_empty_stream():
    response = client.get("/traces")
    assert response.status_code == 200
    assert response.json()["trace_ids"] == []

def test_history_includes_persisted_anomaly_flags():
    """FR-8 / Flow 5: replay must carry the worker-persisted anomaly flags."""
    import asyncio
    from app.redis_client import get_redis

    headers = {"Authorization": "Bearer test-secret-key"}
    span = get_valid_span_payload("an-1")
    span["trace_id"] = "tr-anomaly"
    client.post("/ingest", json=span, headers=headers)

    # Worker-shaped flag in the anomaly stream (same shape ws.py relays live)
    async def _write_flag():
        r = get_redis()
        await r.xadd("agentscope:anomalies", {"payload": json.dumps({
            "rule": "failure_loops", "span_id": "an-1", "trace_id": "tr-anomaly",
            "agent_id": "agent-1",
            "details": {"reason": "Identical call signature seen 4 times within 60s"},
            "is_anomaly": True,
        })})

    asyncio.run(_write_flag())

    response = client.get("/history/tr-anomaly")
    assert response.status_code == 200
    data = response.json()
    assert data["anomalies"] and len(data["anomalies"]) == 1
    flag = data["anomalies"][0]
    assert flag["rule"] == "failure_loops"
    assert flag["span_id"] == "an-1"
    assert flag["is_anomaly"] is True

def test_history_uses_per_trace_anomaly_index_after_migration():
    """Indexed reads must not depend on scanning the shared anomaly stream."""
    import asyncio
    from app.redis_client import get_redis

    headers = {"Authorization": "Bearer test-secret-key"}
    span = get_valid_span_payload("indexed-an-1")
    span["trace_id"] = "tr-indexed-anomaly"
    client.post("/ingest", json=span, headers=headers)
    flag = {
        "rule": "failure_loops",
        "span_id": "indexed-an-1",
        "trace_id": "tr-indexed-anomaly",
        "agent_id": "agent-1",
        "details": {"reason": "indexed"},
        "is_anomaly": True,
    }

    async def _write_index_only():
        r = get_redis()
        await r.rpush("agentscope:anomaly-trace:tr-indexed-anomaly", json.dumps(flag))
        await r.set("agentscope:index:anomalies:v1", "1")

    asyncio.run(_write_index_only())
    response = client.get("/history/tr-indexed-anomaly")
    assert response.status_code == 200
    assert response.json()["anomalies"] == [flag]

def test_history_sorts_legacy_trace_index_by_authoritative_stream_id():
    """Old RPUSH races are repaired at read time by Redis stream-ID order."""
    import asyncio
    from app.redis_client import get_redis

    first = get_valid_span_payload("ordered-1")
    first["trace_id"] = "tr-legacy-order"
    second = get_valid_span_payload("ordered-2")
    second["trace_id"] = "tr-legacy-order"

    async def _write_out_of_order_index():
        r = get_redis()
        id1 = await r.xadd("agentscope:events", {"payload": json.dumps(first)})
        id2 = await r.xadd("agentscope:events", {"payload": json.dumps(second)})
        await r.rpush("agentscope:trace:tr-legacy-order", id2, id1)

    asyncio.run(_write_out_of_order_index())
    response = client.get("/history/tr-legacy-order")
    assert response.status_code == 200
    assert [span["span_id"] for span in response.json()["spans"]] == ["ordered-1", "ordered-2"]

def test_concurrent_ingest_index_matches_authoritative_stream_order():
    headers = {"Authorization": "Bearer test-secret-key"}
    trace_id = "tr-concurrent-order"

    def post(index: int):
        payload = get_valid_span_payload(f"parallel-{index:03d}")
        payload["trace_id"] = trace_id
        response = client.post("/ingest", json=payload, headers=headers)
        assert response.status_code == 200

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(post, range(60)))

    response = client.get(f"/history/{trace_id}")
    assert response.status_code == 200

    import redis
    r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    stream_order = []
    for _message_id, message in r.xrange("agentscope:events"):
        payload = json.loads(message["payload"])
        if payload["trace_id"] == trace_id:
            stream_order.append(payload["span_id"])
    r.close()
    assert [span["span_id"] for span in response.json()["spans"]] == stream_order

def test_history_without_anomalies_omits_field():
    headers = {"Authorization": "Bearer test-secret-key"}
    span = get_valid_span_payload("clean-1")
    span["trace_id"] = "tr-clean"
    client.post("/ingest", json=span, headers=headers)

    response = client.get("/history/tr-clean")
    assert response.status_code == 200
    # No flags persisted -> field stays absent (additive schema, old shape intact)
    assert response.json().get("anomalies") is None
