"""Evaluation-only API server used when Docker/Redis cannot start.

This preserves the real FastAPI ingestion/history/WebSocket code and swaps
only the external Redis process for fakeredis in the same event loop. Results
from this server must be labeled fallback smoke measurements, never production
stack latency claims.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import fakeredis.aioredis
import uvicorn


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "sdk"))
os.environ.setdefault("AGENTSCOPE_API_KEY", "test-key")

from app import history, ingest, redis_client, ws


fake_server = fakeredis.FakeServer()
raw_fake_client = fakeredis.aioredis.FakeRedis(server=fake_server, decode_responses=True)


class FakeRedisCompatibility:
    """Add reliable blocking XREAD/$ behavior missing from fakeredis on Windows."""

    def __init__(self, client):
        self.client = client
        self._dollar_baselines = {}

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def xread(self, streams, count=None, block=None):
        task_id = id(asyncio.current_task())
        resolved = {}
        for stream, cursor in streams.items():
            if cursor != "$":
                resolved[stream] = cursor
                continue
            key = (task_id, stream)
            if key not in self._dollar_baselines:
                latest = await self.client.xrevrange(stream, max="+", min="-", count=1)
                self._dollar_baselines[key] = latest[0][0] if latest else "0-0"
            resolved[stream] = self._dollar_baselines[key]

        deadline = time.monotonic() + ((block or 0) / 1000.0)
        while True:
            result = []
            for stream, cursor in resolved.items():
                cursor_parts = tuple(int(part) for part in str(cursor).split("-", 1))
                rows = await self.client.xrange(stream, min="-", max="+")
                newer = [
                    row
                    for row in rows
                    if tuple(int(part) for part in str(row[0]).split("-", 1)) > cursor_parts
                ]
                if newer:
                    result.append((stream, newer[:count] if count else newer))
            if result or not block or time.monotonic() >= deadline:
                return result
            await asyncio.sleep(0.01)


fake_client = FakeRedisCompatibility(raw_fake_client)


def get_fake_redis():
    return fake_client


redis_client.get_redis = get_fake_redis
ingest.get_redis = get_fake_redis
history.get_redis = get_fake_redis
ws.get_redis = get_fake_redis


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(ingest.app, host=args.host, port=args.port, log_level="warning")
