import os
from fastapi import FastAPI, HTTPException, Request, Depends
from agentscope.schema import Span
from app.redis_client import get_redis
from app.ws import router as ws_router
from app.history import router as history_router

app = FastAPI(title="AgentScope Ingestion API")
app.include_router(ws_router)
app.include_router(history_router)

INGEST_AND_INDEX_SCRIPT = """
local message_id = redis.call('XADD', KEYS[1], '*', 'payload', ARGV[1])
local timestamp_ms = string.match(message_id, '^(%d+)%-')
redis.call('ZADD', KEYS[2], timestamp_ms, ARGV[2])
local payload_index_complete = redis.call('LLEN', KEYS[3]) == redis.call('LLEN', KEYS[4])
redis.call('RPUSH', KEYS[3], message_id)
if payload_index_complete then
    redis.call('RPUSH', KEYS[4], ARGV[1])
end
return message_id
"""

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
    # Append the durable event and read-index entries as one Redis-side
    # operation. Redis serializes scripts, so the per-trace list has exactly
    # the authoritative stream order even with multiple backend workers. New
    # traces also keep an ordered payload list so history needs one LRANGE
    # instead of one XRANGE command per event. If an upgraded deployment has a
    # legacy ID list without matching payloads, the script deliberately leaves
    # that trace on the compatible ID path rather than creating a partial index.
    payload = span.model_dump_json()
    await get_redis().eval(
        INGEST_AND_INDEX_SCRIPT,
        4,
        "agentscope:events",
        "agentscope:traces",
        f"agentscope:trace:{span.trace_id}",
        f"agentscope:trace-payload:{span.trace_id}",
        payload,
        span.trace_id,
    )
    return {"status": "accepted", "span_id": span.span_id}
