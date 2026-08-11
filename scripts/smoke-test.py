import asyncio
import json
import os
import subprocess
import time
import httpx
from websockets import connect

async def run_smoke_test():
    print("Starting AgentScope E2E Smoke Test...")

    # Set up environment
    os.environ["AGENTSCOPE_API_KEY"] = "smoke-test-key"
    
    print("1. Starting Redis (docker-compose)...")
    subprocess.run(["docker-compose", "up", "-d"], cwd="infra", check=True)

    print("2. Starting Uvicorn backend and Worker...")
    # Start the backend server as a subprocess
    backend_proc = subprocess.Popen(
        ["uvicorn", "app.ingest:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd="backend",
        env=os.environ
    )
    
    # Start the anomaly worker
    worker_proc = subprocess.Popen(
        ["python", "main.py"],
        cwd="worker",
        env=os.environ
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

        print("3. Connecting to WebSocket relay...")
        async with connect("ws://127.0.0.1:8000/ws") as websocket:
            print("WebSocket connected.")

            print("4. Sending test crash span via HTTP POST...")
            test_span = {
                "trace_id": "smoke-test-trace",
                "span_id": "smoke-test-span",
                "span_type": "llm_call",
                "name": "SmokeTestNode",
                "start_time": "2026-01-01T00:00:00Z",
                "agent_id": "smoke-test-agent",
                "status": {"status": "error", "exception_details": "intentional test crash"}
            }

            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "http://127.0.0.1:8000/ingest",
                    headers={"Authorization": "Bearer smoke-test-key"},
                    json=test_span
                )
                assert res.status_code == 200, f"Ingest failed: {res.text}"
                print("Span ingested successfully.")

            print("5. Verifying span and anomaly arrival over WebSocket...")
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
        print("6. Cleaning up...")
        backend_proc.terminate()
        backend_proc.wait()
        worker_proc.terminate()
        worker_proc.wait()
        subprocess.run(["docker-compose", "down"], cwd="infra", check=False)
        print("Done.")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
