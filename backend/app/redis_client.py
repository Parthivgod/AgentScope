import os
import redis.asyncio as redis

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Create a connection pool
pool = redis.ConnectionPool.from_url(redis_url, decode_responses=True)
redis_client = redis.Redis(connection_pool=pool)
