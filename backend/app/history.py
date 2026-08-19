import json
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from agentscope.schema import Trace, Span
from app.redis_client import redis_client

router = APIRouter()

@router.get("/history/{trace_id}", response_model=Trace)
async def get_trace_history(
    trace_id: str,
    start_ts: Optional[str] = Query(None, description="Start timestamp for XRANGE bound"),
    end_ts: Optional[str] = Query(None, description="End timestamp for XRANGE bound")
):
    # Determine bounds for XRANGE (default to full stream '-' to '+')
    # If timestamps are provided, they could map to Redis IDs if we tracked them,
    # but XRANGE supports generic ID bounds. Since we don't have secondary indexing yet,
    # we'll fetch a broad range and filter in-memory. 
    # For Sprint 1, we pull the whole stream and filter.
    
    events = await redis_client.xrange("agentscope:events", min="-", max="+")
    
    spans = []
    for message_id, message in events:
        payload = message.get(b"payload") or message.get("payload")
        if payload:
            try:
                span_data = json.loads(payload)
                if span_data.get("trace_id") == trace_id:
                    # Append strictly in arrival order
                    spans.append(Span(**span_data))
            except Exception:
                pass
                
    if not spans:
        raise HTTPException(status_code=404, detail="Trace not found or no spans recorded")
        
    return Trace(trace_id=trace_id, spans=spans)
