from typing import Optional, Dict, Any
from agentscope.schema import Span

class CrashRule:
    name = "crashes"

    def evaluate(self, span: Span) -> Optional[Dict[str, Any]]:
        # 1. Check if status is error (unhandled exception / non-2xx)
        if span.status.status == "error":
            return {"reason": "Span status is error", "exception_details": span.status.exception_details}
        
        # 2. Check for unexpected null/empty LLM completion if span is ended
        if span.span_type == "llm_call" and span.end_time is not None:
            # We assume a completed LLM call should have some output
            if span.output is None or span.output == "" or span.output == {}:
                return {"reason": "LLM call completed with empty output"}
        
        return None
