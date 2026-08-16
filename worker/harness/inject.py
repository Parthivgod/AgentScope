import asyncio
import os
import httpx
from datetime import datetime, timezone

# Optional: harness for injecting anomalies
# This requires hitting the FastAPI ingest endpoint or directly writing to Redis.
# The PRD says it should be tested via the ingestion path so the full stack is validated.

API_KEY = "test-key"
INGEST_URL = "http://127.0.0.1:8000/ingest"

def get_base_span():
    return {
        "trace_id": "synthetic-trace-1",
        "span_id": "span-1",
        "parent_span_id": None,
        "span_type": "llm_call",
        "name": "harness_agent",
        "input": {"prompt": "test"},
        "output": {"response": "test"},
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "status": {"status": "success"},
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        "agent_id": "agent-1"
    }

async def inject_crash():
    print("Injecting Crash...")
    span = get_base_span()
    span["span_id"] = "crash-span-1"
    span["status"] = {"status": "error", "exception_details": "Synthetic crash"}
    async with httpx.AsyncClient() as client:
        await client.post(INGEST_URL, json=span, headers={"Authorization": f"Bearer {API_KEY}"})

async def inject_failure_loop():
    print("Injecting Failure Loop (4 identical calls)...")
    span = get_base_span()
    async with httpx.AsyncClient() as client:
        for i in range(4):
            span["span_id"] = f"loop-span-{i}"
            await client.post(INGEST_URL, json=span, headers={"Authorization": f"Bearer {API_KEY}"})

async def inject_token_spike():
    print("Injecting Token Spike (>8k tokens)...")
    span = get_base_span()
    span["span_id"] = "token-spike-1"
    span["token_usage"] = {"prompt_tokens": 4000, "completion_tokens": 4500, "total_tokens": 8500}
    async with httpx.AsyncClient() as client:
        await client.post(INGEST_URL, json=span, headers={"Authorization": f"Bearer {API_KEY}"})

async def inject_timeout():
    print("Injecting Timeout (>30s)...")
    span = get_base_span()
    span["span_id"] = "timeout-span-1"
    
    # 35 seconds duration
    start = datetime.now(timezone.utc)
    import datetime as dt
    end = start + dt.timedelta(seconds=35)
    
    span["start_time"] = start.isoformat()
    span["end_time"] = end.isoformat()
    
    async with httpx.AsyncClient() as client:
        await client.post(INGEST_URL, json=span, headers={"Authorization": f"Bearer {API_KEY}"})

async def inject_message_storm():
    print("Injecting Message Storm (>20/sec)...")
    span = get_base_span()
    async with httpx.AsyncClient() as client:
        for i in range(25):
            span["span_id"] = f"storm-span-{i}"
            await client.post(INGEST_URL, json=span, headers={"Authorization": f"Bearer {API_KEY}"})

async def inject_delegation_cycle():
    print("Injecting Delegation Cycle (A->B->A)...")
    # A -> B
    span1 = get_base_span()
    span1["span_id"] = "delegation-1"
    span1["span_type"] = "delegation"
    span1["agent_id"] = "agent-A"
    span1["output"] = {"delegated_to": "agent-B"}
    
    # B -> A
    span2 = get_base_span()
    span2["span_id"] = "delegation-2"
    span2["parent_span_id"] = "delegation-1"
    span2["span_type"] = "delegation"
    span2["agent_id"] = "agent-B"
    span2["output"] = {"delegated_to": "agent-A"}
    
    async with httpx.AsyncClient() as client:
        await client.post(INGEST_URL, json=span1, headers={"Authorization": f"Bearer {API_KEY}"})
        await client.post(INGEST_URL, json=span2, headers={"Authorization": f"Bearer {API_KEY}"})

async def run_all():
    await inject_crash()
    await asyncio.sleep(1)
    await inject_failure_loop()
    await asyncio.sleep(1)
    await inject_token_spike()
    await asyncio.sleep(1)
    await inject_timeout()
    await asyncio.sleep(1)
    await inject_message_storm()
    await asyncio.sleep(1)
    await inject_delegation_cycle()
    print("Injection complete.")

if __name__ == "__main__":
    asyncio.run(run_all())
