from typing import Optional, Dict, Any
from agentscope.schema import Span
from datetime import datetime, timezone

class TimeoutRule:
    name = "timeouts"

    def __init__(self, thresholds: Dict[str, Any]):
        # Provisional Sprint 1 baseline threshold, validated via synthetic injection harness.
        # Pending tuning against real traffic patterns (RULES.md §6).
        self.ceiling_seconds = thresholds.get("ceiling_seconds", 30)

    def evaluate(self, span: Span) -> Optional[Dict[str, Any]]:
        # If the span has an end_time, calculate the duration
        if span.end_time:
            duration = (span.end_time - span.start_time).total_seconds()
            if duration > self.ceiling_seconds:
                return {
                    "reason": f"Span duration ({duration:.2f}s) exceeded timeout ceiling ({self.ceiling_seconds}s)",
                    "duration_seconds": duration
                }
        else:
            # If the span hasn't ended yet, we could check against current time
            # However, spans arrive as single events (often just once on end).
            # If it's a start event and we want to detect timeouts, it might be tricky
            # without a periodic tick. For now, we evaluate when we see the event.
            now = datetime.now(timezone.utc)
            duration = (now - span.start_time).total_seconds()
            if duration > self.ceiling_seconds:
                return {
                    "reason": f"Span is incomplete and has already exceeded timeout ceiling ({self.ceiling_seconds}s)",
                    "duration_seconds": duration
                }
                
        return None
