import json
import logging
import re
from datetime import datetime, timezone

import pytest

import agentscope.privacy as privacy
from agentscope.config import reset_redaction_config, set_redaction_enabled
from agentscope.schema import Span
from agentscope.sender import _prepare_span_for_send
from worker.rules.failure_loops import FailureLoopRule


@pytest.fixture(autouse=True)
def redaction_enabled():
    set_redaction_enabled(True)
    yield
    reset_redaction_config()


def _span(span_id: str, sensitive_value: str) -> Span:
    return Span(
        trace_id="privacy-trace",
        span_id=span_id,
        span_type="tool_call",
        name="lookup-sensitive-record",
        input={"secret": sensitive_value},
        output={"result": sensitive_value},
        start_time=datetime.now(timezone.utc),
        agent_id="privacy-agent",
    )


def test_same_sensitive_value_has_same_fingerprint_and_flags_repeat(monkeypatch):
    local_key = b"LOCAL-ONLY-HMAC-KEY-32-BYTES!!"
    monkeypatch.setattr(privacy, "_HMAC_KEY", local_key)

    first = _prepare_span_for_send(_span("same-1", "account-number-12345"))
    second = _prepare_span_for_send(_span("same-2", "account-number-12345"))

    assert first.progress_fingerprint == second.progress_fingerprint
    assert re.fullmatch(r"[0-9a-f]{32}", first.progress_fingerprint)

    rule = FailureLoopRule({"count": 2, "window_seconds": 60})
    assert rule.evaluate(first) is None
    assert rule.evaluate(second) is not None


def test_different_sensitive_values_have_different_fingerprints_and_show_progress(monkeypatch):
    monkeypatch.setattr(privacy, "_HMAC_KEY", b"ANOTHER-LOCAL-HMAC-KEY-32-BYTES")

    first = _prepare_span_for_send(_span("different-1", "account-number-12345"))
    second = _prepare_span_for_send(_span("different-2", "account-number-67890"))

    assert first.progress_fingerprint != second.progress_fingerprint

    rule = FailureLoopRule({"count": 2, "window_seconds": 60})
    assert rule.evaluate(first) is None
    assert rule.evaluate(second) is None


def test_wire_safe_span_contains_no_raw_value_or_hmac_key(monkeypatch, caplog):
    raw_value = "TOP-SECRET-PATIENT-RECORD-998877"
    local_key = b"VISIBLE-ONLY-INSIDE-THIS-TEST-KEY"
    monkeypatch.setattr(privacy, "_HMAC_KEY", local_key)

    with caplog.at_level(logging.DEBUG):
        prepared = _prepare_span_for_send(_span("wire-safe", raw_value))

    serialized = prepared.model_dump_json()
    payload = json.loads(serialized)

    assert payload["input"] == "[REDACTED]"
    assert payload["output"] == "[REDACTED]"
    assert payload["progress_fingerprint"]
    assert raw_value not in serialized
    assert raw_value not in caplog.text
    assert local_key.decode("ascii") not in serialized
    assert local_key.hex() not in serialized
