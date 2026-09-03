import os
import asyncio

import redis.asyncio as redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

# redis.asyncio connections bind to the event loop that creates them. A single
# module-level client breaks when used from several event loops in one process
# (e.g. starlette TestClient portals in the test suite: the second loop gets
# "Event loop is closed"). get_redis() therefore returns one client per loop.
_clients: dict[int, redis.Redis] = {}

# A Redis restart invalidates sockets already checked into the pool.  Without a
# health check/retry policy, the first request after recovery can consume one of
# those stale sockets and fail even though Redis is healthy again.  Keep the
# retry window bounded: the API must recover promptly, while the SDK remains
# fail-silent and asynchronous if the store stays unavailable.
REDIS_HEALTH_CHECK_INTERVAL_SECONDS = 1
REDIS_RETRY_ATTEMPTS = 5
REDIS_RETRY_BACKOFF = ExponentialBackoff(cap=0.5, base=0.05)


def get_redis() -> redis.Redis:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    key = id(loop) if loop is not None else 0
    client = _clients.get(key)
    if client is None:
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            health_check_interval=REDIS_HEALTH_CHECK_INTERVAL_SECONDS,
            retry=Retry(REDIS_RETRY_BACKOFF, retries=REDIS_RETRY_ATTEMPTS),
        )
        _clients[key] = client
    return client
