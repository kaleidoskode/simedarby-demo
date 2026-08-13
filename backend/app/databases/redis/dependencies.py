from redis.asyncio import Redis

from app.databases.redis.db import RedisService

# Instantiate the RedisService
redis_service = RedisService()


async def get_redis() -> Redis:
    """Return the shared Redis client instance."""
    return await redis_service.get_client()
