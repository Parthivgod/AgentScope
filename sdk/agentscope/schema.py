from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

class TokenUsage(BaseModel):
    """
    Tracks token counts for LLM calls (prompt, completion, and total).
    """
    prompt_tokens: Optional[int] = 0
    completion_tokens: Optional[int] = 0
    total_tokens: Optional[int] = 0

class SpanStatus(BaseModel):
    """
    Execution status of a span ('success' or 'error'), including stringified exception details if failed.
    """
    status: Literal["success", "error"] = Field("success", description="Status indicator")
    exception_details: Optional[str] = Field(None, description="Exception details if status is error")

class Span(BaseModel):
    """
    Core event unit representing a discrete operation within an agent run.
    Produced by both Flow 1 (LangGraphAdapter) and Flow 2 (@trace / patch) integration paths.
    """
    trace_id: str = Field(..., description="Unique ID for the full agent run")
    span_id: str = Field(..., description="This call's ID")
    parent_span_id: Optional[str] = Field(None, description="This call's causal parent")
    span_type: Literal["llm_call", "tool_call", "delegation", "state_update"] = Field(..., description="Type of span")
    name: str = Field(..., description="Name of the operation (e.g., search_web, gpt-4o.complete)")
    
    input: Optional[Any] = Field(None, description="Captured arguments (subject to redaction policy)")
    output: Optional[Any] = Field(None, description="Captured response (subject to redaction policy)")
    
    start_time: datetime = Field(..., description="When the span started")
    end_time: Optional[datetime] = Field(None, description="When the span ended")
    
    status: SpanStatus = Field(default_factory=SpanStatus, description="Status of the span including exception details")
    
    token_usage: Optional[TokenUsage] = Field(None, description="Prompt/completion tokens")
    agent_id: str = Field(..., description="Which agent/node made the call")

class Trace(BaseModel):
    """
    Container representing a collection of ordered spans belonging to a single agent execution trace.
    """
    trace_id: str = Field(..., description="Unique ID for the full agent run")
    spans: List[Span] = Field(default_factory=list, description="List of spans in this trace")
    start_time: datetime = Field(..., description="When the trace started")
    end_time: Optional[datetime] = Field(None, description="When the trace ended")
    status: Literal["success", "error"] = Field("success", description="Overall status of the trace")
    # Anomaly flags detected for this trace (worker-written, FR-8 replay parity
    # with the live WS path). Optional/additive: absent for producers that
    # only report spans, so existing payloads stay valid. Raw flag payloads
    # carry {rule, span_id, trace_id, agent_id, details, is_anomaly}.
    anomalies: Optional[List[Dict[str, Any]]] = Field(None, description="Anomaly flags for this trace, in arrival order")
