import os
import json
from fastapi import FastAPI, HTTPException, Request, Depends
from agentscope.schema import Span
from app.redis_client import get_redis
from app.ws import router as ws_router
from app.history import router as history_router

app = FastAPI(title="AgentScope Ingestion API")
app.include_router(ws_router)
app.include_router(history_router)

# Middleware / Dependency for API Key validation
async def verify_api_key(request: Request):
    api_key = request.headers.get("Authorization")
    expected_key = os.environ.get("AGENTSCOPE_API_KEY")
    
    # FR-7: Ingestion endpoint SHALL reject requests without a valid API key
    if not expected_key:
        # If no key configured on server, reject all or warn (assuming reject to be safe as per rules)
        raise HTTPException(status_code=500, detail="Server misconfiguration: AGENTSCOPE_API_KEY not set")
    
    if api_key != f"Bearer {expected_key}" and api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key

@app.post("/ingest", dependencies=[Depends(verify_api_key)])
async def ingest_span(span: Span):
    # Validates incoming payloads against the Span schema from sdk/agentscope/schema.py
    # Write to Redis Streams (durable, ordered)
    payload = span.model_dump_json()
    message_id = await get_redis().xadd("agentscope:events", {"payload": payload})
    # Per-trace read index: lets /history and /traces serve in O(trace size)
    # instead of scanning the whole event stream (Week 9 load-test finding).
    # Additive keys only — the worker still reads agentscope:events unchanged.
    try:
        ts_ms = int(str(message_id).split("-")[0])
        await get_redis().zadd("agentscope:traces", {span.trace_id: ts_ms})
        await get_redis().rpush(f"agentscope:trace:{span.trace_id}", str(message_id))
    except Exception:
        # Index maintenance must never break ingestion (RULES.md §3.1/#6)
        pass
    return {"status": "accepted", "span_id": span.span_id}
