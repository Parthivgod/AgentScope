"""Ingest-only profile to isolate the write path from read-path event-loop blocking."""
from locustfile import make_span
from locust import HttpUser, task, between
import os

class IngestOnly(HttpUser):
    wait_time = between(0.01, 0.05)
    def on_start(self):
        self.api_key = os.environ.get("AGENTSCOPE_API_KEY", "test-key")
    @task
    def ingest(self):
        self.client.post("/ingest", json=make_span("loadtest-ingestonly"),
                         headers={"Authorization": f"Bearer {self.api_key}"},
                         name="POST /ingest (auth)")
