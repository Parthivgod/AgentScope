from datetime import datetime, timedelta, timezone

from agentscope.schema import Span
from worker.rules.failure_loops import FailureLoopRule


BASE = datetime(2026, 8, 31, tzinfo=timezone.utc)


def span(trace_id: str, span_id: str, offset: int = 0, completed: bool = False) -> Span:
    return Span(
        trace_id=trace_id,
        span_id=span_id,
        span_type="tool_call",
        name="retry-tool",
        input={"same": True},
        output={"ok": True} if completed else None,
        start_time=BASE + timedelta(seconds=offset),
        end_time=BASE + timedelta(seconds=offset + 1) if completed else None,
        agent_id="shared-agent",
    )


def test_identical_calls_in_different_traces_do_not_merge():
    rule = FailureLoopRule({"count": 4, "window_seconds": 60})
    for index in range(4):
        assert rule.evaluate(span(f"trace-{index}", f"call-{index}", index)) is None


def test_lifecycle_versions_count_once_and_emit_once():
    rule = FailureLoopRule({"count": 4, "window_seconds": 60})
    for index in range(3):
        active = span("one-trace", f"call-{index}", index)
        assert rule.evaluate(active) is None
        assert rule.evaluate(active.model_copy(update={"end_time": active.start_time + timedelta(seconds=1)})) is None

    fourth = span("one-trace", "call-3", 3)
    assert rule.evaluate(fourth) is not None
    assert rule.evaluate(fourth.model_copy(update={"end_time": fourth.start_time + timedelta(seconds=1)})) is None
