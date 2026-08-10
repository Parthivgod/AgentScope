import pytest
import os
import sys
from unittest.mock import AsyncMock, patch as mock_patch
from fastapi.testclient import TestClient

# Add backend and sdk to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sdk")))

from app.ingest import app as ingest_app
from linear_agent import run_linear_agent
from branching_agent import run_branching_agent

client = TestClient(ingest_app)

@pytest.mark.asyncio
async def test_langgraph_demo_spans_sent_to_real_ingest():
    os.environ["AGENTSCOPE_API_KEY"] = "demo-api-key"
    os.environ["AGENTSCOPE_INGEST_URL"] = "http://testserver/ingest"

    received_spans = []

    def mock_post(url, json=None, headers=None):
        response = client.post("/ingest", json=json, headers=headers)
        if response.status_code == 200:
            received_spans.append(json)
        return response

    with mock_patch("backend.app.ingest.redis_client.xadd", new_callable=AsyncMock) as mock_xadd, \
         mock_patch("httpx.AsyncClient.post", side_effect=mock_post):

        # Run linear demo agent
        linear_res = await run_linear_agent(agent_id="e2e-linear-agent", trace_id="trace-e2e-linear")
        assert "output_text" in linear_res

        # Run branching demo agent
        branching_res = await run_branching_agent("Calculate 10 + 20", agent_id="e2e-branching-agent", trace_id="trace-e2e-branching")
        assert "result" in branching_res

        # Verify spans received by real /ingest endpoint
        assert len(received_spans) > 0
        for span_json in received_spans:
            assert "trace_id" in span_json
            assert "span_id" in span_json
            assert "span_type" in span_json
            assert span_json["agent_id"] in ["e2e-linear-agent", "e2e-branching-agent"]
            
        assert mock_xadd.called
