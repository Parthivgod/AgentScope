from typing import Optional, Dict, Any
from agentscope.schema import Span
from datetime import datetime
import json
import hashlib

class FailureLoopRule:
    name = "failure_loops"

    def __init__(self, thresholds: Dict[str, Any]):
        # Frozen baseline validated on the synthetic corpus; field tuning remains pending.
        self.count_threshold = thresholds.get("count", 4)
        self.window_seconds = thresholds.get("window_seconds", 60)
        # A loop is meaningful only within one execution. Keying by agent_id
        # alone merged unrelated traces during concurrent load. The inner map
        # deduplicates active/completed lifecycle versions of the same call.
        # (trace_id, agent_id) -> span_id -> (timestamp, signature)
        self.history: Dict[tuple[str, str], Dict[str, tuple[datetime, str]]] = {}

    def _get_signature(self, span: Span) -> str:
        # Under client-side redaction, compare the keyed pre-redaction
        # fingerprint rather than the identical literal "[REDACTED]" value.
        if span.progress_fingerprint:
            comparison_value = f"hmac:{span.progress_fingerprint}"
        else:
            try:
                comparison_value = json.dumps(span.input, sort_keys=True) if span.input else ""
            except TypeError:
                comparison_value = str(span.input)
        sig_raw = f"{span.name}:{comparison_value}"
        return hashlib.sha256(sig_raw.encode('utf-8')).hexdigest()

    def evaluate(self, span: Span) -> Optional[Dict[str, Any]]:
        # We only care about tool calls or llm calls for loops
        if span.span_type not in ("llm_call", "tool_call"):
            return None

        scope = (span.trace_id, span.agent_id)
        now = span.start_time
        sig = self._get_signature(span)

        calls = self.history.setdefault(scope, {})

        # Prune old calls outside the window before considering this event.
        self.history[scope] = calls = {
            span_id: (timestamp, signature)
            for span_id, (timestamp, signature) in calls.items()
            if (now - timestamp).total_seconds() <= self.window_seconds
        }

        previous = calls.get(span.span_id)
        calls[span.span_id] = (now, sig)
        if previous == (now, sig):
            # The SDK emits active and completed versions with the same span
            # identity/start time. A lifecycle update is not another call and
            # must not emit the same loop finding twice.
            return None

        # Count occurrences of the current signature
        sig_count = sum(1 for _timestamp, signature in calls.values() if signature == sig)

        if sig_count >= self.count_threshold:
            return {
                "reason": f"Identical call signature seen {sig_count} times within {self.window_seconds}s",
                "signature": sig
            }

        return None
