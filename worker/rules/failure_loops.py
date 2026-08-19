from typing import Optional, Dict, Any, List
from agentscope.schema import Span
from datetime import datetime
import json
import hashlib

class FailureLoopRule:
    name = "failure_loops"

    def __init__(self, thresholds: Dict[str, Any]):
        # Provisional Sprint 1 baseline thresholds, validated via synthetic injection harness.
        # Pending tuning against real traffic patterns (RULES.md §6).
        self.count_threshold = thresholds.get("count", 4)
        self.window_seconds = thresholds.get("window_seconds", 60)
        # state: agent_id -> list of (timestamp, signature)
        self.history: Dict[str, List[tuple[datetime, str]]] = {}

    def _get_signature(self, span: Span) -> str:
        # A simple state hash: name + stringified input
        try:
            input_str = json.dumps(span.input, sort_keys=True) if span.input else ""
        except TypeError:
            input_str = str(span.input)
        sig_raw = f"{span.name}:{input_str}"
        return hashlib.sha256(sig_raw.encode('utf-8')).hexdigest()

    def evaluate(self, span: Span) -> Optional[Dict[str, Any]]:
        # We only care about tool calls or llm calls for loops
        if span.span_type not in ("llm_call", "tool_call"):
            return None

        agent_id = span.agent_id
        now = span.start_time
        sig = self._get_signature(span)

        if agent_id not in self.history:
            self.history[agent_id] = []

        # Add current call
        self.history[agent_id].append((now, sig))

        # Prune old calls outside the window
        self.history[agent_id] = [
            (t, s) for t, s in self.history[agent_id]
            if (now - t).total_seconds() <= self.window_seconds
        ]

        # Count occurrences of the current signature
        sig_count = sum(1 for t, s in self.history[agent_id] if s == sig)

        if sig_count >= self.count_threshold:
            return {
                "reason": f"Identical call signature seen {sig_count} times within {self.window_seconds}s",
                "signature": sig
            }

        return None
