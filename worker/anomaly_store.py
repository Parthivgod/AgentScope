"""Durable anomaly persistence with a per-trace read index."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any


ANOMALIES_STREAM = "agentscope:anomalies"
ANOMALY_TRACE_PREFIX = "agentscope:anomaly-trace:"
ANOMALY_INDEX_READY = "agentscope:index:anomalies:v1"


def anomaly_trace_key(trace_id: str) -> str:
    return f"{ANOMALY_TRACE_PREFIX}{trace_id}"


async def ensure_anomaly_index(redis_client) -> None:
    """Build the index once for anomaly records created before this version.

    Ingestion is independent of the worker, so this startup migration cannot
    stall or reject monitored-agent traffic (RULES.md invariant #6).
    """
    if await redis_client.get(ANOMALY_INDEX_READY):
        return

    by_trace: dict[str, list[str]] = defaultdict(list)
    for _message_id, message in await redis_client.xrange(ANOMALIES_STREAM, min="-", max="+"):
        payload = message.get("payload") or message.get(b"payload")
        if not payload:
            continue
        try:
            trace_id = json.loads(payload).get("trace_id")
        except (TypeError, json.JSONDecodeError):
            continue
        if trace_id:
            by_trace[trace_id].append(payload)

    pipe = redis_client.pipeline(transaction=True)
    for trace_id, payloads in by_trace.items():
        key = anomaly_trace_key(trace_id)
        pipe.delete(key)
        pipe.rpush(key, *payloads)
    pipe.set(ANOMALY_INDEX_READY, "1")
    await pipe.execute()


async def persist_anomaly(redis_client, anomaly: dict[str, Any]) -> None:
    """Append an anomaly and its trace index entry in one Redis transaction."""
    payload = json.dumps(anomaly)
    pipe = redis_client.pipeline(transaction=True)
    pipe.xadd(ANOMALIES_STREAM, {"payload": payload})
    pipe.rpush(anomaly_trace_key(anomaly["trace_id"]), payload)
    await pipe.execute()
