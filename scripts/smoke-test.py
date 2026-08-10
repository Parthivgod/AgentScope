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

    print("2. Starting Uvicorn backend...")
    # Start the backend server as a subprocess
    backend_proc = subprocess.Popen(
        ["uvicorn", "app.ingest:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd="backend",
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

            print("4. Sending test span via HTTP POST...")
            test_span = {
                "trace_id": "smoke-test-trace",
                "span_id": "smoke-test-span",
                "span_type": "llm_call",
                "name": "SmokeTestNode",
                "start_time": "2026-01-01T00:00:00Z",
                "agent_id": "smoke-test-agent",
                "inputs": {"test": "data"}
            }

            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "http://127.0.0.1:8000/ingest",
                    headers={"Authorization": "Bearer smoke-test-key"},
                    json=test_span
                )
                assert res.status_code == 200, f"Ingest failed: {res.text}"
                print("Span ingested successfully.")

            print("5. Verifying span arrival over WebSocket...")
            # Wait up to 5 seconds for the message to propagate through Redis and WS
            msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(msg)
            
            assert data.get("span_id") == "smoke-test-span", "Received span ID does not match"
            print("SUCCESS: Real span arrived over WebSocket relay.")

    finally:
        print("6. Cleaning up...")
        backend_proc.terminate()
        backend_proc.wait()
        subprocess.run(["docker-compose", "down"], cwd="infra", check=False)
        print("Done.")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
