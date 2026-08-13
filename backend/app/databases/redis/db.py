import logging

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from app.databases.redis.config import Config

logger = logging.getLogger(__name__)


class RedisService:
    """Service for managing the Redis connection.

    Redis carries the two pieces of the booking flow that must be shared by
    every worker: the seat locks (short lived keys with a TTL) and the per
    showtime event stream that both the WebSocket and the polling endpoint
    read from.
    """

    def __init__(self):
        """Initialize the service with empty pool and client containers."""
        self.pool = None    # Stores the Redis connection pool
        self.client = None  # Stores the Redis client instance

    def connect(self) -> Redis:
        """Establish and return the Redis connection, reusing it if present."""

        # If the connection already exists, reuse it
        if self.client is not None:
            return self.client

        redis_url = Config.set_redis()

        # decode_responses keeps every reply as str, so lock holders and stream
        # payloads do not need decoding at each call site.
        self.pool = ConnectionPool.from_url(
            redis_url,
            decode_responses=True,
            max_connections=50,
            health_check_interval=30,
        )
        self.client = Redis(connection_pool=self.pool)
        logger.info("Connected to Redis")

        return self.client

    async def get_client(self) -> Redis:
        """Return the Redis client instance."""
        return self.connect()

    async def close(self):
        """Close the client and release the pooled connections."""
        if self.client is not None:
            await self.client.aclose()
            self.client = None
        if self.pool is not None:
            await self.pool.disconnect()
            self.pool = None
