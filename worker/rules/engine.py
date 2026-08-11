from typing import List, Dict, Any
from agentscope.schema import Span
import logging

logger = logging.getLogger(__name__)

# Provisional thresholds pending injection-harness validation (Sprint 1 starting values)
# See RULES.md §2 Decision 3
THRESHOLDS = {
    "failure_loops": {"count": 4, "window_seconds": 60},
    "timeouts": {"ceiling_seconds": 30},
    "token_spikes": {"single_call": 8000, "session_rate": 20000}, # per minute
    "message_storms": {"count": 20, "window_seconds": 5},
}

class AnomalyEngine:
    def __init__(self):
        # We instantiate the rules here.
        # They will maintain their own state.
        from .crashes import CrashRule
        from .failure_loops import FailureLoopRule
        from .timeouts import TimeoutRule
        from .token_spikes import TokenSpikeRule
        from .message_storms import MessageStormRule
        from .delegation_cycles import DelegationCycleRule

        self.rules = [
            CrashRule(),
            FailureLoopRule(THRESHOLDS["failure_loops"]),
            TimeoutRule(THRESHOLDS["timeouts"]),
            TokenSpikeRule(THRESHOLDS["token_spikes"]),
            MessageStormRule(THRESHOLDS["message_storms"]),
            DelegationCycleRule(),
        ]

    def evaluate(self, span: Span) -> List[Dict[str, Any]]:
        """
        Evaluates a span against all rules.
        Returns a list of anomaly payloads if any rules trigger.
        """
        anomalies = []
        for rule in self.rules:
            try:
                result = rule.evaluate(span)
                if result:
                    anomalies.append({
                        "rule": rule.name,
                        "span_id": span.span_id,
                        "trace_id": span.trace_id,
                        "agent_id": span.agent_id,
                        "details": result
                    })
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.name}: {e}")
                # Fail silent on rule evaluation error
        return anomalies
