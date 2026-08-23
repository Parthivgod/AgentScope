import pytest
import os
import sys
from unittest.mock import AsyncMock, patch as mock_patch
from fastapi.testclient import TestClient

# Add backend and sdk to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sdk")))

from app.ingest import app as ingest_app
from custom_agent import run_custom_agent

client = TestClient(ingest_app)

@pytest.mark.asyncio
async def test_custom_demo_agent_spans_sent_to_ingest():
    os.environ["AGENTSCOPE_API_KEY"] = "demo-api-key"
    os.environ["AGENTSCOPE_INGEST_URL"] = "http://testserver/ingest"

    received_spans = []

    def mock_post(url, json=None, headers=None):
        response = client.post("/ingest", json=json, headers=headers)
        if response.status_code == 200:
            received_spans.append(json)
        return response

    mock_redis = AsyncMock()

    with mock_patch("app.ingest.get_redis", return_value=mock_redis), \
         mock_patch("httpx.AsyncClient.post", side_effect=mock_post):

        # Run custom demo agent
        res = await run_custom_agent(query="Test Query", agent_id="custom-e2e-agent", trace_id="trace-custom-e2e")
        assert res["status"] == "success"
        assert "summary" in res

        # Give background queue worker a moment to process sent spans
        import asyncio
        await asyncio.sleep(0.2)

        # Verify spans received by real /ingest endpoint
        assert len(received_spans) >= 3
        for span_json in received_spans:
            assert "trace_id" in span_json
            assert "span_id" in span_json
            assert "span_type" in span_json
            assert "name" in span_json
            assert span_json["agent_id"] in {
                "custom-e2e-agent",
                "custom-demo-agent",
                "web-data-tool",
                "result-processor",
                "summary-generator",
            }
            assert span_json["status"]["status"] == "success"

        assert mock_redis.xadd.called
