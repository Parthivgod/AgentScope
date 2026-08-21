"""
Week 10 Track B resilience tests (PRD §10 Test #6, RULES.md invariants #6, FR-4).

Three checks against the local docker-compose stack:
  worker-kill : ingest continuously while the worker is killed mid-stream;
                no ingestion errors, no event loss; after worker restart it
                catches up (last_id advances) — worker isolation (invariant #6).
  redis-restart: restart Redis mid-run; ingestion continues, and with AOF
                persistence no accepted events are lost (FR-4).
  slow-ws     : a WebSocket client that connects and never reads; ingest
                throughput/latency must be unaffected (backend doesn't block
                on a slow consumer).

Usage: python scripts/resilience-stack.py {worker-kill|redis-restart|slow-ws}
"""

import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
INGEST = "http://localhost/ingest"  # through Nginx
HEADERS = {"Authorization": "Bearer test-key"}


def make_span(trace_id):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "trace_id": trace_id, "span_id": str(uuid.uuid4()), "parent_span_id": None,
        "span_type": "tool_call", "name": "resilience-node",
        "input": {"i": True}, "output": None,
        "start_time": now, "end_time": now,
        "status": {"status": "success", "exception_details": None},
        "token_usage": None, "agent_id": "resilience-agent",
    }


def redis(*args):
    r = subprocess.run(["docker", "compose", "exec", "-T", "redis", "redis-cli", *args],
                       cwd=str(REPO / "infra"), capture_output=True, text=True)
    return r.stdout.strip()


def compose(*args):
    return subprocess.run(["docker", "compose", *args], cwd=str(REPO / "infra"),
                          capture_output=True, text=True)


def ingest(client, trace_id):
    resp = client.post(INGEST, json=make_span(trace_id), headers=HEADERS)
    assert resp.status_code == 200, f"ingest failed: {resp.status_code} {resp.text}"
    return 1


def test_worker_kill():
    trace = f"resilience-wk-{uuid.uuid4().hex[:6]}"
    count = 0
    with httpx.Client(timeout=10.0) as client:
        # Phase 1: ingest while worker alive
        for _ in range(20):
            count += ingest(client, trace)
        before_last = redis("GET", "agentscope:worker:last_id")

        # Phase 2: kill worker mid-stream, keep ingesting
        compose("stop", "worker")
        for _ in range(30):
            count += ingest(client, trace)

        xlen_while_down = int(redis("XLEN", "agentscope:events"))
        compose("start", "worker")
        time.sleep(5)

        # Phase 3: more ingestion after restart
        for _ in range(20):
            count += ingest(client, trace)

    xlen_final = int(redis("XLEN", "agentscope:events"))
    after_last = redis("GET", "agentscope:worker:last_id")
    anomalies = int(redis("XLEN", "agentscope:anomalies"))

    print(f"  ingested total (this test): {count}")
    print(f"  stream length while worker down: {xlen_while_down} (>= 50 means ingestion unaffected)")
    print(f"  stream length final: {xlen_final}")
    print(f"  worker last_id before kill: {before_last!r} / after restart: {after_last!r}")
    print(f"  anomalies processed by worker: {anomalies}")
    ok = xlen_while_down >= 50 and after_last not in (None, "", before_last) and xlen_final >= 70
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def test_redis_restart():
    trace = f"resilience-rr-{uuid.uuid4().hex[:6]}"
    with httpx.Client(timeout=10.0) as client:
        for _ in range(20):
            ingest(client, trace)
        pre_xlen = int(redis("XLEN", "agentscope:events"))

        print("  restarting redis...")
        t0 = time.time()
        compose("restart", "redis")
        print(f"  compose restart returned after {time.time()-t0:.1f}s")

        # FR-4: previously ACCEPTED events must still be there (AOF persistence)
        post_xlen = int(redis("XLEN", "agentscope:events"))

        # Ingestion must resume without a stall once Redis is back (transient
        # 5xx during the restart window itself is expected — Redis is the store).
        recovered, failures = False, 0
        for attempt in range(60):
            try:
                ingest(client, trace)
                recovered = True
                break
            except AssertionError:
                failures += 1
                time.sleep(1)
        recover_s = attempt + 1
        final_xlen = int(redis("XLEN", "agentscope:events"))
        for _ in range(19):
            ingest(client, trace)
        final_xlen2 = int(redis("XLEN", "agentscope:events"))

    print(f"  XLEN pre-restart: {pre_xlen}, immediately post-restart: {post_xlen} (no loss = {post_xlen >= pre_xlen})")
    print(f"  ingestion recovered after ~{recover_s}s ({failures} transient failures during window)")
    print(f"  XLEN after recovery + 20 more: {final_xlen2}")
    ok = post_xlen >= pre_xlen and recovered and final_xlen2 >= post_xlen + 20
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def test_slow_ws():
    import websockets  # noqa

    async def _run():
        import asyncio
        trace = f"resilience-sw-{uuid.uuid4().hex[:6]}"
        latency_no_ws, latency_slow_ws = [], []

        async def measure():
            async with httpx.AsyncClient(timeout=10.0) as client:
                for _ in range(50):
                    t0 = time.perf_counter()
                    r = await client.post(INGEST, json=make_span(trace), headers=HEADERS)
                    assert r.status_code == 200
                    latency_no_ws.append((time.perf_counter() - t0) * 1000)

        await measure()  # baseline, no WS client

        # Slow client: connect, then STOP reading (fill OS buffers)
        import websockets
        slow = await websockets.connect("ws://localhost/ws", max_queue=1)
        await asyncio.sleep(0.5)

        async with httpx.AsyncClient(timeout=10.0) as client:
            for _ in range(200):
                t0 = time.perf_counter()
                r = await client.post(INGEST, json=make_span(trace), headers=HEADERS)
                assert r.status_code == 200
                latency_slow_ws.append((time.perf_counter() - t0) * 1000)
        # never recv() on slow — leave it hanging; close without draining
        await slow.close()

        def stats(xs):
            xs = sorted(xs)
            return xs[len(xs)//2], xs[int(len(xs)*0.95)]

        b_p50, b_p95 = stats(latency_no_ws)
        s_p50, s_p95 = stats(latency_slow_ws)
        print(f"  ingest p50/p95 without WS client: {b_p50:.0f}/{b_p95:.0f}ms")
        print(f"  ingest p50/p95 with stalled WS client: {s_p50:.0f}/{s_p95:.0f}ms")
        ok = s_p95 < 500 and s_p95 < b_p95 * 5  # no pathological blocking
        print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
        return ok

    import asyncio
    return asyncio.run(_run())


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"worker-kill": test_worker_kill, "redis-restart": test_redis_restart, "slow-ws": test_slow_ws}
    print(f"--- resilience-stack: {which} ---")
    sys.exit(0 if fn[which]() else 1)
