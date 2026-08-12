import pytest
import os
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from agentscope.schema import Span, SpanStatus
from agentscope.config import is_redaction_enabled, set_redaction_enabled, reset_redaction_config
from agentscope.sender import AsyncEventSender

@pytest.fixture(autouse=True)
def cleanup_redaction():
    reset_redaction_config()
    yield
    reset_redaction_config()

def test_redaction_config_defaults():
    os.environ.pop("AGENTSCOPE_REDACT_ENABLED", None)
    reset_redaction_config()
    assert is_redaction_enabled() is False

def test_redaction_config_env_var():
    os.environ["AGENTSCOPE_REDACT_ENABLED"] = "true"
    reset_redaction_config()
    assert is_redaction_enabled() is True

    os.environ["AGENTSCOPE_REDACT_ENABLED"] = "false"
    reset_redaction_config()
    assert is_redaction_enabled() is False

def test_redaction_config_programmatic():
    set_redaction_enabled(True)
    assert is_redaction_enabled() is True

    set_redaction_enabled(False)
    assert is_redaction_enabled() is False

@pytest.mark.asyncio
async def test_client_side_redaction_in_sender():
    set_redaction_enabled(True)
    sender_instance = AsyncEventSender()

    posted_json = None

    async def mock_post(url, json=None, headers=None):
        nonlocal posted_json
        posted_json = json
        class MockResponse:
            status_code = 200
            def raise_for_status(self): pass
        return MockResponse()

    sender_instance.client.post = AsyncMock(side_effect=mock_post)

    span = Span(
        trace_id="test-redact-trace",
        span_id="span-123",
        span_type="tool_call",
        name="sensitive_tool",
        input={"secret_key": "super_secret_password"},
        output={"secret_result": "confidential_user_data"},
        start_time=datetime.now(timezone.utc),
        agent_id="test-agent"
    )

    sender_instance.send(span)
    await asyncio.sleep(0.1)

    assert posted_json is not None
    assert posted_json["input"] == "[REDACTED]"
    assert posted_json["output"] == "[REDACTED]"
    assert posted_json["trace_id"] == "test-redact-trace"
    assert posted_json["name"] == "sensitive_tool"
