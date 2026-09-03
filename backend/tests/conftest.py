"""Shared fixtures for backend tests.

Cleanup uses a *synchronous* Redis client on purpose: the async connection
pool binds its connections to whichever event loop first uses it, so calling
``asyncio.run()`` per test (each with a fresh, then-closed loop) crashes with
``RuntimeError: Event loop is closed`` on Windows/ProactorEventLoop — the
issue that previously made test_ws.py/test_history.py fail locally.
"""
import os

# Isolate tests onto Redis DB 15 BEFORE the app (and its redis_client module)
# is imported: the default DB 0 is the LIVE dockerized stack, where the real
# anomaly worker consumes and flags test traffic, and test cleanup would flush
# the running stack's data. DB 15 has no worker — pure test data.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest
import redis as sync_redis


def _clean_redis():
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    r = sync_redis.Redis.from_url(url, decode_responses=True)
    keys = [
        "agentscope:events",
        "agentscope:traces",
        "agentscope:anomalies",
        "agentscope:worker:last_id",
        "agentscope:index:anomalies:v1",
    ]
    keys += r.keys("agentscope:trace:*")
    keys += r.keys("agentscope:trace-payload:*")
    keys += r.keys("agentscope:anomaly-trace:*")
    if keys:
        r.delete(*keys)
    r.close()


@pytest.fixture(autouse=True)
def clean_redis():
    _clean_redis()
    yield
    _clean_redis()
