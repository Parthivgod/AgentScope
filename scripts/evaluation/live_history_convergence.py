"""Black-box convergence tests for live WebSocket and historical replay paths."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import websockets

from common import distribution, environment_manifest, write_json


SEED = 20260830


def make_span(trace_id: str, span_id: str, completed: bool) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": None,
        "span_type": "tool_call",
        "name": f"convergence-{span_id}",
        "input": {"phase": "completed" if completed else "active"},
        "output": {"ok": True} if completed else None,
        "start_time": now,
        "end_time": now if completed else None,
        "status": {"status": "success", "exception_details": None},
        "token_usage": None,
        "agent_id": "convergence-agent",
    }


def signature(span: dict[str, Any]) -> tuple[str, str | None, str]:
    return (span["span_id"], span.get("end_time"), span["status"]["status"])


def latest_by_span(spans: list[dict[str, Any]]) -> dict[str, tuple[str, str | None, str]]:
    latest = {}
    for span in spans:
        latest[span["span_id"]] = signature(span)
    return latest


async def post_many(client: httpx.AsyncClient, ingest_url: str, api_key: str, spans: list[dict]) -> list[float]:
    async def post(span):
        started = time.perf_counter()
        response = await client.post(
            ingest_url,
            json=span,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        return (time.perf_counter() - started) * 1000.0

    return await asyncio.gather(*(post(span) for span in spans))


async def receive_trace(ws, trace_id: str, expected: int, timeout: float) -> list[dict]:
    events = []
    deadline = asyncio.get_running_loop().time() + timeout
    while len(events) < expected:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        payload = json.loads(raw)
        if payload.get("trace_id") == trace_id and not payload.get("is_anomaly"):
            events.append(payload)
    return events


async def synchronize(ws, client, ingest_url: str, api_key: str) -> None:
    trace_id = f"convergence-handshake-{uuid.uuid4().hex}"
    marker = make_span(trace_id, "handshake", True)
    for _ in range(3):
        await asyncio.sleep(0.15)
        await post_many(client, ingest_url, api_key, [marker])
        if await receive_trace(ws, trace_id, 1, 2.0):
            return
    raise RuntimeError("WebSocket could not be synchronized with the event stream")


async def fetch_history(client: httpx.AsyncClient, base_url: str, trace_id: str) -> list[dict]:
    response = await client.get(f"{base_url}/history/{trace_id}")
    response.raise_for_status()
    return response.json()["spans"]


def compare(trace_id: str, live: list[dict], historical: list[dict], expected: int) -> dict[str, Any]:
    live_signatures = [signature(span) for span in live]
    history_signatures = [signature(span) for span in historical]
    live_counter = Counter(live_signatures)
    history_counter = Counter(history_signatures)
    missing = list((history_counter - live_counter).elements())
    extra = list((live_counter - history_counter).elements())
    live_latest = latest_by_span(live)
    history_latest = latest_by_span(historical)
    latest_mismatches = sorted(
        span_id
        for span_id in set(live_latest) | set(history_latest)
        if live_latest.get(span_id) != history_latest.get(span_id)
    )
    return {
        "trace_id": trace_id,
        "expected_event_count": expected,
        "live_event_count": len(live),
        "history_event_count": len(historical),
        "event_multiset_equal": live_counter == history_counter,
        "arrival_order_equal": live_signatures == history_signatures,
        "latest_state_equal": not latest_mismatches,
        "missing_live_event_count": len(missing),
        "extra_live_event_count": len(extra),
        "latest_state_mismatch_count": len(latest_mismatches),
        "latest_state_mismatch_span_ids": latest_mismatches,
        "missing_live_signatures": missing[:20],
        "extra_live_signatures": extra[:20],
    }


async def connected_run(ws, client, ingest_url, base_url, api_key, size, repetition):
    trace_id = f"convergence-connected-{size}-{repetition}-{uuid.uuid4().hex[:8]}"
    span_ids = [f"node-{index:04d}" for index in range(size)]
    post_ms = []
    post_ms.extend(await post_many(client, ingest_url, api_key, [make_span(trace_id, sid, False) for sid in span_ids]))
    post_ms.extend(await post_many(client, ingest_url, api_key, [make_span(trace_id, sid, True) for sid in span_ids]))
    live = await receive_trace(ws, trace_id, size * 2, timeout=15.0)
    historical = await fetch_history(client, base_url, trace_id)
    result = compare(trace_id, live, historical, size * 2)
    result.update(
        {
            "scenario": "continuously_connected_burst",
            "burst_span_count": size,
            "repetition": repetition,
            "post_latency_ms": distribution(post_ms),
        }
    )
    return result


async def reconnect_gap(client, ingest_url, base_url, ws_url, api_key):
    trace_id = f"convergence-reconnect-{uuid.uuid4().hex[:8]}"
    span_ids = [f"node-{index:04d}" for index in range(10)]
    async with websockets.connect(ws_url, max_queue=16384) as first_ws:
        await synchronize(first_ws, client, ingest_url, api_key)
        await post_many(client, ingest_url, api_key, [make_span(trace_id, sid, False) for sid in span_ids])
        live = await receive_trace(first_ws, trace_id, len(span_ids), timeout=10.0)

    last_event_id = live[-1].get("_agentscope_stream_id")
    if not last_event_id:
        raise RuntimeError("WebSocket event did not include a resumable stream cursor")

    await post_many(client, ingest_url, api_key, [make_span(trace_id, sid, True) for sid in span_ids])

    parts = urlsplit(ws_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["last_event_id"] = last_event_id
    resumed_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    async with websockets.connect(resumed_url, max_queue=16384) as second_ws:
        live.extend(await receive_trace(second_ws, trace_id, len(span_ids), timeout=10.0))

    historical = await fetch_history(client, base_url, trace_id)
    result = compare(trace_id, live, historical, len(span_ids) * 2)
    result.update(
        {
            "scenario": "disconnect_during_completions_then_reconnect",
            "burst_span_count": len(span_ids),
            "resume_cursor": last_event_id,
            "expected_behavior": "events after the supplied durable cursor are replayed before new events",
        }
    )
    return result


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default=os.environ.get("CONVERGENCE_BASE_URL", "http://localhost"))
    parser.add_argument("--ws-url", default=os.environ.get("CONVERGENCE_WS_URL", "ws://localhost/ws"))
    args = parser.parse_args()
    ingest_url = f"{args.base_url.rstrip('/')}/ingest"
    api_key = os.environ.get("AGENTSCOPE_API_KEY", "test-key")
    connected = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        async with websockets.connect(args.ws_url, max_queue=16384) as ws:
            await synchronize(ws, client, ingest_url, api_key)
            for size in (10, 50, 100):
                for repetition in range(3):
                    connected.append(
                        await connected_run(
                            ws, client, ingest_url, args.base_url, api_key, size, repetition
                        )
                    )
        reconnect = await reconnect_gap(client, ingest_url, args.base_url, args.ws_url, api_key)

    payload = {
        "study": "live_historical_convergence",
        "manifest": environment_manifest(SEED, " ".join(sys.argv)),
        "design": {
            "environment_label": os.environ.get("EVALUATION_ENVIRONMENT", "unspecified"),
            "continuous_sizes": [10, 50, 100],
            "repetitions_per_size": 3,
            "events_per_span": 2,
            "comparison": "event multiset, stream order, and dashboard-equivalent latest span state",
        },
        "continuous_connection": {
            "runs": connected,
            "event_multiset_passes": sum(run["event_multiset_equal"] for run in connected),
            "arrival_order_passes": sum(run["arrival_order_equal"] for run in connected),
            "latest_state_passes": sum(run["latest_state_equal"] for run in connected),
            "run_count": len(connected),
        },
        "reconnect_gap": reconnect,
    }
    write_json(args.output, payload)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "continuous_latest_state_passes": f"{payload['continuous_connection']['latest_state_passes']}/{len(connected)}",
                "reconnect_latest_state_equal": reconnect["latest_state_equal"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
