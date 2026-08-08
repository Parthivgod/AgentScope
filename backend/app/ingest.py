import os
import json
from fastapi import FastAPI, HTTPException, Request, Depends
from agentscope.schema import Span
from app.redis_client import redis_client

app = FastAPI(title="AgentScope Ingestion API")

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
    await redis_client.xadd("agentscope:events", {"payload": payload})
    return {"status": "accepted", "span_id": span.span_id}
