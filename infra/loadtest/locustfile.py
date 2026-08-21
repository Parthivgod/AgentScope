"""
Week 9 load test (NFR 9.1, PRD §10 Test #4) — Locust against the LOCAL
docker-compose stack THROUGH NGINX (port 80), not FastAPI directly.

Traffic mix mirrors realistic dashboard/SDK usage:
  - POST /ingest with valid API key (SDK sender traffic) — weight 5
  - GET  /traces (dashboard replay dropdown)               — weight 2
  - GET  /history/{trace_id} (dashboard replay fetch)      — weight 2
  - POST /ingest without key (must 401; guards FR-7 under load) — weight 1

Run headless from this directory:
    locust --headless -u 50 -r 10 -t 60s --csv results/week9 --html results/week9.html \
        --host http://localhost
"""

import json
import random
import uuid
from datetime import datetime, timezone

from locust import HttpUser, task, between


def make_span(trace_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "trace_id": trace_id,
        "span_id": str(uuid.uuid4()),
        "parent_span_id": None,
        "span_type": random.choice(["llm_call", "tool_call", "delegation", "state_update"]),
        "name": f"loadtest-node-{random.randint(1, 5)}",
        "input": {"prompt": "load test"},
        "output": {"response": "ok"},
        "start_time": now,
        "end_time": now,
        "status": {"status": "success", "exception_details": None},
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "agent_id": "loadtest-agent",
    }


class AgentScopeUser(HttpUser):
    wait_time = between(0.01, 0.05)

    def on_start(self):
        import os
        self.api_key = os.environ.get("AGENTSCOPE_API_KEY", "test-key")
        self.trace_id = f"loadtest-{uuid.uuid4().hex[:8]}"
        # Seed one span so /history for this trace exists
        self.client.post(
            "/ingest", json=make_span(self.trace_id),
            headers={"Authorization": f"Bearer {self.api_key}"},
            name="POST /ingest (seed)",
        )

    @task(5)
    def ingest(self):
        self.client.post(
            "/ingest", json=make_span(self.trace_id),
            headers={"Authorization": f"Bearer {self.api_key}"},
            name="POST /ingest (auth)",
        )

    @task(2)
    def traces(self):
        self.client.get("/traces", name="GET /traces")

    @task(2)
    def history(self):
        self.client.get(f"/history/{self.trace_id}", name="GET /history/[id]")

    @task(1)
    def ingest_unauthenticated(self):
        with self.client.post("/ingest", json=make_span(self.trace_id), name="POST /ingest (no key)", catch_response=True) as resp:
            if resp.status_code == 401:
                resp.success()  # 401 is the expected, correct behavior (FR-7)
            else:
                resp.failure(f"expected 401, got {resp.status_code}")
