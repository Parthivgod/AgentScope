"""
Week 10 Track A redaction wire test (RULES.md §4 / Decision #4, PRD §10 Test #7).

Proves scrubbed fields are genuinely absent from the bytes that LEAVE the SDK
process: a local stub ingest server records every request body received;
with redaction enabled, the raw payload content must not appear in any of
them — not merely be hidden downstream.
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agentscope.config import set_redaction_enabled, reset_redaction_config
from agentscope.schema import Span, SpanStatus
from agentscope.sender import AsyncEventSender
from datetime import datetime, timezone

SECRET_INPUT = "SUPER-SECRET-PROMPT-DO-NOT-LEAK-8675309"
SECRET_OUTPUT = "SUPER-SECRET-COMPLETION-DO-NOT-LEAK-4242"


class RecordingHandler(BaseHTTPRequestHandler):
    bodies = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        RecordingHandler.bodies.append(body)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture
def stub_ingest():
    server = HTTPServer(("127.0.0.1", 0), RecordingHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    RecordingHandler.bodies = []
    yield f"http://127.0.0.1:{port}/ingest"
    server.shutdown()


def make_span():
    now = datetime.now(timezone.utc).isoformat()
    return Span(
        trace_id="t-wire", span_id="s-wire", parent_span_id=None,
        span_type="llm_call", name="gpt-test",
        input={"prompt": SECRET_INPUT}, output={"text": SECRET_OUTPUT},
        start_time=now, end_time=now,
        status=SpanStatus(status="success"), agent_id="wire-agent",
    )


def run_sender_and_drain(url):
    import asyncio
    sender = AsyncEventSender()
    os.environ["AGENTSCOPE_API_KEY"] = "test-key"
    os.environ["AGENTSCOPE_INGEST_URL"] = url

    async def drain():
        # send() inside the loop so the fail-silent worker task starts
        sender.send(make_span())
        await sender.queue.join()
        await sender.client.aclose()

    asyncio.run(drain())


def test_redacted_fields_absent_from_wire(stub_ingest):
    set_redaction_enabled(True)
    try:
        run_sender_and_drain(stub_ingest)
    finally:
        reset_redaction_config()

    assert len(RecordingHandler.bodies) >= 1, "stub server received no requests"
    for body in RecordingHandler.bodies:
        text = body.decode("utf-8")
        assert SECRET_INPUT not in text, "raw input leaked onto the wire"
        assert SECRET_OUTPUT not in text, "raw output leaked onto the wire"
        payload = json.loads(text)
        assert payload["input"] == "[REDACTED]"
        assert payload["output"] == "[REDACTED]"


def test_full_capture_default_leaks_by_design(stub_ingest):
    # Default is full capture (Decision #4): raw payloads DO leave the process.
    run_sender_and_drain(stub_ingest)
    assert any(SECRET_INPUT in b.decode() for b in RecordingHandler.bodies)
