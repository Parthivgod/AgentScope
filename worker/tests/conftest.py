import os

import pytest_asyncio
import redis.asyncio as redis


TEST_REDIS_URL = os.environ.get("AGENTSCOPE_WORKER_TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest_asyncio.fixture
async def redis_client():
    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
