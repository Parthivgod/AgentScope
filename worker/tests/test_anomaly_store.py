import json

import pytest

from worker.anomaly_store import (
    ANOMALIES_STREAM,
    ANOMALY_INDEX_READY,
    anomaly_trace_key,
    ensure_anomaly_index,
    persist_anomaly,
)


@pytest.mark.asyncio
async def test_persist_anomaly_updates_stream_and_trace_index(redis_client):
    anomaly = {"trace_id": "trace-a", "span_id": "span-a", "rule": "crashes"}
    await persist_anomaly(redis_client, anomaly)

    stream = await redis_client.xrange(ANOMALIES_STREAM)
    indexed = await redis_client.lrange(anomaly_trace_key("trace-a"), 0, -1)
    assert json.loads(stream[0][1]["payload"]) == anomaly
    assert [json.loads(payload) for payload in indexed] == [anomaly]


@pytest.mark.asyncio
async def test_startup_migrates_legacy_anomalies(redis_client):
    anomaly = {"trace_id": "legacy-trace", "span_id": "legacy-span", "rule": "timeouts"}
    await redis_client.xadd(ANOMALIES_STREAM, {"payload": json.dumps(anomaly)})

    await ensure_anomaly_index(redis_client)

    assert await redis_client.get(ANOMALY_INDEX_READY) == "1"
    indexed = await redis_client.lrange(anomaly_trace_key("legacy-trace"), 0, -1)
    assert [json.loads(payload) for payload in indexed] == [anomaly]
