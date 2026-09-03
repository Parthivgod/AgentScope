import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
import httpx
import redis
from websockets import connect


def stop_process(process: subprocess.Popen, grace_seconds: float = 5.0) -> None:
    """Stop a child without turning a successful smoke assertion into failure."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=grace_seconds)

async def run_smoke_test():
    print("Starting AgentScope E2E Smoke Test...")

    env = os.environ.copy()
    env.setdefault("AGENTSCOPE_API_KEY", "smoke-test-key")
    env.setdefault("REDIS_URL", "redis://127.0.0.1:6379/14")

    # Redis is an explicit prerequisite. CI supplies it as a service; local
    # users can start just Redis with `docker compose -f infra/docker-compose.yml
    # up -d redis`. DB 14 keeps this destructive smoke-test cleanup isolated
    # from the normal stack on DB 0 and backend unit tests on DB 15.
    store = redis.Redis.from_url(env["REDIS_URL"], decode_responses=True)
    try:
        store.ping()
    except redis.RedisError as exc:
        raise RuntimeError(
            "Redis is required for the smoke test; start the Redis service first"
        ) from exc
    store.flushdb()

    print("1. Starting Uvicorn backend and worker...")
    # Start the backend server as a subprocess
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.ingest:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd="backend",
        env=env
    )
    
    # Start the anomaly worker
    worker_proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd="worker",
        env=env
    )

    try:
        # Wait for backend to start
        for _ in range(30):
            try:
                res = httpx.get("http://127.0.0.1:8000/docs")
                if res.status_code == 200:
                    print("Backend started successfully.")
                    break
            except httpx.RequestError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Backend failed to start within 15 seconds.")

        print("2. Connecting to WebSocket relay...")
        async with connect("ws://127.0.0.1:8000/ws") as websocket:
            print("WebSocket connected.")

            print("3. Sending test crash span via HTTP POST...")
            now = datetime.now(timezone.utc).isoformat()
            test_span = {
                "trace_id": "smoke-test-trace",
                "span_id": "smoke-test-span",
                "span_type": "llm_call",
                "name": "SmokeTestNode",
                "start_time": now,
                "agent_id": "smoke-test-agent",
                "status": {"status": "error", "exception_details": "intentional test crash"}
            }

            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "http://127.0.0.1:8000/ingest",
                    headers={"Authorization": f"Bearer {env['AGENTSCOPE_API_KEY']}"},
                    json=test_span
                )
                assert res.status_code == 200, f"Ingest failed: {res.text}"
                print("Span ingested successfully.")

            print("4. Verifying span and anomaly arrival over WebSocket...")
            # We expect two messages (one event, one anomaly) since worker processes it and writes to anomaly stream
            msg1 = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data1 = json.loads(msg1)
            
            msg2 = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data2 = json.loads(msg2)
            
            messages = [data1, data2]
            
            event_received = any("span_id" in d and not d.get("is_anomaly") for d in messages)
            anomaly_received = any(d.get("is_anomaly") for d in messages)
            
            assert event_received, "Normal event not received"
            assert anomaly_received, "Anomaly flag not received"
            
            print("SUCCESS: Both span and anomaly arrived over WebSocket relay.")

    finally:
        print("5. Cleaning up...")
        # Uvicorn can wait on an outstanding blocking Redis XREAD after SIGTERM
        # on Linux. Escalate to kill after a bounded grace period, and always
        # stop both children even if one needs escalation.
        stop_process(backend_proc)
        stop_process(worker_proc)
        try:
            store.flushdb()
        finally:
            store.close()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
