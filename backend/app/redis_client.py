import os
import asyncio
from typing import Optional

import redis.asyncio as redis

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

# redis.asyncio connections bind to the event loop that creates them. A single
# module-level client breaks when used from several event loops in one process
# (e.g. starlette TestClient portals in the test suite: the second loop gets
# "Event loop is closed"). get_redis() therefore returns one client per loop.
_clients: dict[int, redis.Redis] = {}


def get_redis() -> redis.Redis:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    key = id(loop) if loop is not None else 0
    client = _clients.get(key)
    if client is None:
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        _clients[key] = client
    return client
