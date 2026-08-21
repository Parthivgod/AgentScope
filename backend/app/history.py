import json
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from agentscope.schema import Trace, Span
from app.redis_client import get_redis

router = APIRouter()

EVENTS_STREAM = "agentscope:events"
TRACES_ZSET = "agentscope:traces"
TRACE_LIST_PREFIX = "agentscope:trace:"


async def _scan_stream():
    """Full-stream scan (legacy path). Returns the raw (message_id, payload_json) list
    in strict arrival order. Used only as a fallback/rebuild path for events written
    before the per-trace index existed (Week 9 load-test optimization)."""
    events = await get_redis().xrange(EVENTS_STREAM, min="-", max="+")
    result = []
    for message_id, message in events:
        payload = message.get(b"payload") or message.get("payload")
        if payload:
            result.append((str(message_id), payload))
    return result


async def _indexed_message_ids(trace_id: str) -> list[str]:
    """Message IDs for a trace from the per-trace index, in arrival order."""
    ids = await get_redis().lrange(f"{TRACE_LIST_PREFIX}{trace_id}", 0, -1)
    return [str(i) for i in ids]


async def _rebuild_index_for_trace(trace_id: str, scanned: list[tuple[str, str]]) -> None:
    """Populate the per-trace index entries discovered during a fallback scan."""
    try:
        pipe = get_redis().pipeline(transaction=False)
        first = True
        for message_id, payload in scanned:
            try:
                span_data = json.loads(payload)
            except Exception:
                continue
            if span_data.get("trace_id") != trace_id:
                continue
            ts_ms = int(message_id.split("-")[0])
            pipe.zadd(TRACES_ZSET, {trace_id: ts_ms})
            pipe.rpush(f"{TRACE_LIST_PREFIX}{trace_id}", message_id)
            first = False
        if not first:
            await pipe.execute()
    except Exception:
        pass


@router.get("/traces")
async def list_traces():
    """List distinct trace IDs present in the event stream, most recently active first."""
    trace_ids = await get_redis().zrevrange(TRACES_ZSET, 0, -1)
    if trace_ids:
        return {"trace_ids": trace_ids}

    # Index empty — fall back to a full scan (pre-index data) and rebuild.
    scanned = await _scan_stream()
    if not scanned:
        return {"trace_ids": []}
    last_seen: dict[str, str] = {}
    for message_id, payload in scanned:
        try:
            trace_id = json.loads(payload).get("trace_id")
        except Exception:
            continue
        if trace_id:
            last_seen[trace_id] = message_id
    try:
        pipe = get_redis().pipeline(transaction=False)
        for trace_id, message_id in last_seen.items():
            pipe.zadd(TRACES_ZSET, {trace_id: int(message_id.split("-")[0])})
        await pipe.execute()
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
    span_payloads: list[str] = []

    # Fast path: per-trace index (O(trace size), Week 9 load-test optimization)
    message_ids = await _indexed_message_ids(trace_id)
    if message_ids:
        pipe = get_redis().pipeline(transaction=False)
        for mid in message_ids:
            pipe.xrange(EVENTS_STREAM, min=mid, max=mid)
        for rows in await pipe.execute():
            for _mid, message in rows:
                payload = message.get(b"payload") or message.get("payload")
                if payload:
                    span_payloads.append(payload)

    if not span_payloads:
        # No index entries, or the index outlived the stream (e.g. events were
        # trimmed/flushed): legacy full-stream scan, preserving strict arrival
        # order (RULES.md invariant #4). Rebuilds the index for this trace.
        # Legacy fallback: full-stream scan, preserving strict arrival order
        # (RULES.md invariant #4). Rebuilds the index for this trace.
        scanned = await _scan_stream()
        for message_id, payload in scanned:
            try:
                if json.loads(payload).get("trace_id") == trace_id:
                    span_payloads.append(payload)
            except Exception:
                pass
        if span_payloads:
            await _rebuild_index_for_trace(trace_id, scanned)

    spans = []
    for payload in span_payloads:
        try:
            spans.append(Span(**json.loads(payload)))
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
