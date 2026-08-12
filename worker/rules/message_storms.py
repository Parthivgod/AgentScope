from typing import Optional, Dict, Any, List
from agentscope.schema import Span
from datetime import datetime

class MessageStormRule:
    name = "message_storms"

    def __init__(self, thresholds: Dict[str, Any]):
        self.count = thresholds.get("count", 20)
        self.window_seconds = thresholds.get("window_seconds", 5)
        
        # trace_id -> list of timestamps
        self.history: Dict[str, List[datetime]] = {}

    def evaluate(self, span: Span) -> Optional[Dict[str, Any]]:
        trace_id = span.trace_id
        now = span.start_time

        if trace_id not in self.history:
            self.history[trace_id] = []

        self.history[trace_id].append(now)

        # Prune old events
        self.history[trace_id] = [
            t for t in self.history[trace_id]
            if (now - t).total_seconds() <= self.window_seconds
        ]

        event_count = len(self.history[trace_id])

        if event_count > self.count:
            return {
                "reason": f"Message storm detected: {event_count} events in the last {self.window_seconds}s (threshold {self.count})",
                "event_count": event_count
            }

        return None
