from typing import Dict, Optional

from app.core.config import Settings


class Config:
    """Handles MySQL configuration.

    The URI map is resolved lazily and memoised. Building it eagerly at import
    time made every module that merely imports this package require MySQL
    credentials to be present, which is not the case for deployments that only
    use MongoDB and Redis.
    """

    _databases: Optional[Dict[str, str]] = None

    @classmethod
    def databases(cls) -> Dict[str, str]:
        """Return the configured MySQL URIs, resolving them on first use."""
        if cls._databases is None:
            cls._databases = Settings().mysql_config
        return cls._databases

    @staticmethod
    def get_database_url(name):
        """Retrieve the database URL by name."""
        return Config.databases().get(name)
