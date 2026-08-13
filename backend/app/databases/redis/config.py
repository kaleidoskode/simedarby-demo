from typing import Optional

from app.core.config import Settings


class Config:
    """Handles Redis configuration for seat locks and the event stream."""

    _url: Optional[str] = None

    @classmethod
    def set_redis(cls) -> str:
        """Return the Redis connection URL, resolving it on first use."""
        if cls._url is None:
            cls._url = Settings().redis_config['url']
        return cls._url
