import pytest
import json
import os
from fastapi.testclient import TestClient
from datetime import datetime, timezone
from app.ingest import app

@pytest.fixture(autouse=True)
def set_env():
    os.environ["AGENTSCOPE_API_KEY"] = "test-secret-key"
    yield
    if "AGENTSCOPE_API_KEY" in os.environ:
        del os.environ["AGENTSCOPE_API_KEY"]

def test_ws_order_and_complex_payloads():
    client = TestClient(app)
    
    # 1. Connect WS client (starts listening from '$')
    with client.websocket_connect("/ws") as websocket:
        
        # 2. Ingest synthetic events with complex payloads
        event1 = {
            "trace_id": "t1", "span_id": "s1", "parent_span_id": None, "span_type": "delegation", 
            "name": "agent1", "input": {"nested": {"field": True}}, "output": None,
            "start_time": datetime.now(timezone.utc).isoformat(), "end_time": None,
            "status": {"status": "success", "exception_details": None},
            "token_usage": None, "agent_id": "a1"
        }
        
        event2 = {
            "trace_id": "t1", "span_id": "s2", "parent_span_id": "s1", "span_type": "llm_call", 
            "name": "gpt-4", "input": {"prompt": "hello"}, "output": None,
            "start_time": datetime.now(timezone.utc).isoformat(), "end_time": None,
            "status": {"status": "success", "exception_details": None},
            "token_usage": None, "agent_id": "a1"
        }
        
        event3 = {
            "trace_id": "t1", "span_id": "s2", "parent_span_id": "s1", "span_type": "llm_call", 
            "name": "gpt-4", "input": {"prompt": "hello"}, "output": "hi",
            "start_time": datetime.now(timezone.utc).isoformat(), 
            "end_time": datetime.now(timezone.utc).isoformat(),
            "status": {"status": "error", "exception_details": "Rate limit exceeded"},
            "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, 
            "agent_id": "a1"
        }
        
        headers = {"Authorization": "Bearer test-secret-key"}
        client.post("/ingest", json=event1, headers=headers)
        client.post("/ingest", json=event2, headers=headers)
        client.post("/ingest", json=event3, headers=headers)
        
        # 3. Read events from WS
        data1 = websocket.receive_text()
        data2 = websocket.receive_text()
        data3 = websocket.receive_text()
        
        parsed1 = json.loads(data1)
        parsed2 = json.loads(data2)
        parsed3 = json.loads(data3)
        
        # 4. Assert strict arrival order (RULES.md §3 invariant #4)
        assert parsed1["span_id"] == "s1"
        assert parsed2["span_id"] == "s2"
        assert parsed3["span_id"] == "s2"
        
        # 5. Assert complex payload integrity (Week 4 readiness)
        assert parsed1["input"]["nested"]["field"] is True
        assert parsed3["status"]["status"] == "error"
        assert parsed3["status"]["exception_details"] == "Rate limit exceeded"
        assert parsed3["token_usage"]["total_tokens"] == 15
        assert parsed1["_agentscope_stream"] == "agentscope:events"
        assert parsed1["_agentscope_stream_id"]
        assert parsed1["_agentscope_event_cursor"] == parsed1["_agentscope_stream_id"]
        assert parsed1["_agentscope_anomaly_cursor"] == "0-0"

def test_ws_reconnect_replays_events_after_supplied_cursor():
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-secret-key"}
    active = {
        "trace_id": "resume-trace", "span_id": "resume-span", "parent_span_id": None,
        "span_type": "tool_call", "name": "resumable", "input": {"phase": "active"},
        "output": None, "start_time": datetime.now(timezone.utc).isoformat(), "end_time": None,
        "status": {"status": "success", "exception_details": None},
        "token_usage": None, "agent_id": "resume-agent",
    }

    with client.websocket_connect("/ws") as websocket:
        client.post("/ingest", json=active, headers=headers)
        first = json.loads(websocket.receive_text())

    completed = dict(active)
    completed["output"] = {"ok": True}
    completed["end_time"] = datetime.now(timezone.utc).isoformat()
    client.post("/ingest", json=completed, headers=headers)

    cursor = first["_agentscope_stream_id"]
    with client.websocket_connect(f"/ws?last_event_id={cursor}") as websocket:
        replayed = json.loads(websocket.receive_text())

    assert replayed["trace_id"] == "resume-trace"
    assert replayed["span_id"] == "resume-span"
    assert replayed["end_time"] is not None
    assert replayed["_agentscope_stream_id"] != cursor

def test_ws_reconnect_replays_first_anomaly_from_disconnect_gap():
    import asyncio
    from app.redis_client import get_redis

    client = TestClient(app)
    headers = {"Authorization": "Bearer test-secret-key"}
    active = {
        "trace_id": "resume-anomaly-trace", "span_id": "resume-anomaly-span",
        "parent_span_id": None, "span_type": "tool_call", "name": "resumable-anomaly",
        "input": {}, "output": None, "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": None, "status": {"status": "success", "exception_details": None},
        "token_usage": None, "agent_id": "resume-agent",
    }

    with client.websocket_connect("/ws") as websocket:
        client.post("/ingest", json=active, headers=headers)
        first = json.loads(websocket.receive_text())

    anomaly = {
        "rule": "crashes", "span_id": active["span_id"], "trace_id": active["trace_id"],
        "agent_id": active["agent_id"], "details": {"reason": "gap"}, "is_anomaly": True,
    }

    async def _write_anomaly():
        await get_redis().xadd("agentscope:anomalies", {"payload": json.dumps(anomaly)})

    asyncio.run(_write_anomaly())
    query = (
        f"/ws?last_event_id={first['_agentscope_event_cursor']}"
        f"&last_anomaly_id={first['_agentscope_anomaly_cursor']}"
    )
    with client.websocket_connect(query) as websocket:
        replayed = json.loads(websocket.receive_text())

    assert replayed["is_anomaly"] is True
    assert replayed["trace_id"] == active["trace_id"]
    assert replayed["_agentscope_stream"] == "agentscope:anomalies"
