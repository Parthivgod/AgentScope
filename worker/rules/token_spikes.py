from typing import Optional, Dict, Any, List
from agentscope.schema import Span
from datetime import datetime

class TokenSpikeRule:
    name = "token_spikes"

    def __init__(self, thresholds: Dict[str, Any]):
        self.single_call = thresholds.get("single_call", 8000)
        self.session_rate = thresholds.get("session_rate", 20000)
        
        # trace_id -> list of (timestamp, total_tokens)
        self.history: Dict[str, List[tuple[datetime, int]]] = {}

    def evaluate(self, span: Span) -> Optional[Dict[str, Any]]:
        if not span.token_usage or not span.token_usage.total_tokens:
            return None

        tokens = span.token_usage.total_tokens
        
        # Rule 1: Single call > single_call threshold
        if tokens > self.single_call:
            return {
                "reason": f"Single call token usage ({tokens}) exceeded threshold ({self.single_call})",
                "tokens": tokens
            }

        # Rule 2: Session cumulative > session_rate (tokens/min)
        trace_id = span.trace_id
        now = span.end_time or span.start_time

        if trace_id not in self.history:
            self.history[trace_id] = []

        self.history[trace_id].append((now, tokens))

        # Prune older than 1 minute (60s)
        self.history[trace_id] = [
            (t, tok) for t, tok in self.history[trace_id]
            if (now - t).total_seconds() <= 60
        ]

        # Calculate sum
        cumulative_tokens = sum(tok for t, tok in self.history[trace_id])

        if cumulative_tokens > self.session_rate:
            return {
                "reason": f"Cumulative token usage ({cumulative_tokens}) in the last minute exceeded threshold ({self.session_rate})",
                "cumulative_tokens": cumulative_tokens
            }

        return None
