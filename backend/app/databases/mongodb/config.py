from typing import Dict, Optional

from app.core.config import Settings


class Config:
    """Handles application configuration, including database settings.

    The URI map is resolved lazily and memoised so that importing this module
    never requires credentials to already be present in the environment.
    """

    _databases: Optional[Dict[str, str]] = None

    @classmethod
    def databases(cls) -> Dict[str, str]:
        """Return the configured MongoDB URIs, resolving them on first use."""
        if cls._databases is None:
            cls._databases = Settings().mongo_config
        return cls._databases

    @staticmethod
    def set_mongo(name: str) -> str:
        """Retrieve MongoDB URL for a given database name."""
        database_url = Config.databases().get(name)
        if not database_url:
            raise ValueError(
                f"Database '{name}' not found in the configuration.")
        return database_url
