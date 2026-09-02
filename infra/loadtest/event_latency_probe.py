"""
Week 9 event-to-dashboard latency probe (NFR 9.1 / FR-3, PRD §10 Test #4).

Measures the metric the <200ms p95 target actually names: time from a span
being POSTed to /ingest (through Nginx) until that exact span arrives on a
/dashboard WebSocket connection (/ws through Nginx). Run this WHILE a
background Locust load generates realistic concurrent traffic.

Usage:
    AGENTSCOPE_API_KEY=test-key python event_latency_probe.py [--samples 200] [--concurrency 5]
"""

import argparse
import asyncio
import json
import os
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import websockets

INGEST_URL = os.environ.get("PROBE_INGEST_URL", "http://localhost/ingest")
WS_URL = os.environ.get("PROBE_WS_URL", "ws://localhost/ws")


def make_span(marker: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "trace_id": f"probe-{marker}",
        "span_id": marker,
        "parent_span_id": None,
        "span_type": "tool_call",
        "name": f"probe-{marker}",
        "input": {"probe": True},
        "output": {"ok": True},
        "start_time": now,
        "end_time": now,
        "status": {"status": "success", "exception_details": None},
        "token_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "agent_id": "latency-probe",
    }


async def probe_once(client, api_key, pending):
    marker = uuid.uuid4().hex
    future = asyncio.get_event_loop().create_future()
    pending[marker] = future
    try:
        t0 = asyncio.get_event_loop().time()
        resp = await client.post(INGEST_URL, json=make_span(marker),
                                 headers={"Authorization": f"Bearer {api_key}"})
        resp.raise_for_status()
        await asyncio.wait_for(future, timeout=10.0)
        return (asyncio.get_event_loop().time() - t0) * 1000.0
    finally:
        pending.pop(marker, None)


async def reader(ws, pending):
    """Single WS reader: routes each message to the future waiting on its span_id."""
    while True:
        raw = await ws.recv()
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        fut = pending.get(payload.get("span_id"))
        if fut and not fut.done():
            fut.set_result(True)


async def worker(client, api_key, samples_each, pending, results, errors):
    for _ in range(samples_each):
        try:
            results.append(await probe_once(client, api_key, pending))
        except Exception as e:
            print(f"  probe error: {e}")
            errors.append(str(e))


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


async def main(samples: int, concurrency: int, json_output: Path | None) -> None:
    api_key = os.environ.get("AGENTSCOPE_API_KEY", "test-key")
    results: list[float] = []
    errors: list[str] = []
    pending: dict[str, asyncio.Future] = {}
    async with websockets.connect(WS_URL, max_queue=4096) as ws:
        reader_task = asyncio.get_event_loop().create_task(reader(ws, pending))
        async with httpx.AsyncClient(timeout=10.0) as client:
            base, remainder = divmod(samples, concurrency)
            await asyncio.gather(*[
                worker(client, api_key, base + (1 if index < remainder else 0), pending, results, errors)
                for index in range(concurrency)
            ])
        reader_task.cancel()

    results.sort()
    summary = {
        "study": "event_to_dashboard_latency",
        "environment_label": os.environ.get("EVALUATION_ENVIRONMENT", "unspecified"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ingest_url": INGEST_URL,
        "websocket_url": WS_URL,
        "requested_samples": samples,
        "concurrency": concurrency,
        "completed_samples": len(results),
        "error_count": len(errors),
        "errors": errors,
        "latency_ms": {
            "p50": percentile(results, 0.50),
            "p95": percentile(results, 0.95),
            "p99": percentile(results, 0.99),
            "min": min(results) if results else None,
            "max": max(results) if results else None,
            "mean": statistics.mean(results) if results else None,
        },
        "raw_latency_ms": results,
    }
    if not results:
        raise RuntimeError("No latency samples completed")
    print(f"\n=== Event-to-dashboard latency (ingest->WS), n={len(results)} ===")
    print(f"  p50={summary['latency_ms']['p50']:.1f}ms  p95={summary['latency_ms']['p95']:.1f}ms  p99={summary['latency_ms']['p99']:.1f}ms  "
          f"min={results[0]:.1f}ms  max={results[-1]:.1f}ms  mean={statistics.mean(results):.1f}ms")
    if json_output:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"  JSON: {json_output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.samples, args.concurrency, args.json_output))
