import json
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from agentscope.schema import Trace, Span
from app.redis_client import redis_client

router = APIRouter()

@router.get("/traces")
async def list_traces():
    """List distinct trace IDs present in the event stream, most recently active first."""
    events = await redis_client.xrange("agentscope:events", min="-", max="+")

    last_seen: dict[str, str] = {}
    for message_id, message in events:
        payload = message.get(b"payload") or message.get("payload")
        if not payload:
            continue
        try:
            span_data = json.loads(payload)
            trace_id = span_data.get("trace_id")
            if trace_id:
                last_seen[trace_id] = message_id
        except Exception:
            pass

    trace_ids = sorted(last_seen.keys(), key=lambda t: last_seen[t], reverse=True)
    return {"trace_ids": trace_ids}


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
        
    start_time = min(span.start_time for span in spans)
    end_time_candidates = [span.end_time for span in spans if span.end_time]
    end_time = max(end_time_candidates) if end_time_candidates else None
    status = "error" if any(span.status.status == "error" for span in spans) else "success"
        
    return Trace(
        trace_id=trace_id, 
        spans=spans, 
        start_time=start_time, 
        end_time=end_time, 
        status=status
    )
