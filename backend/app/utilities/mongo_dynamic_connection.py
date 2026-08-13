"""
MongoDB Dynamic Connection Manager
Provides dynamic MongoDB database access with error handling.
"""

import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.middleware.exception import CustomErrorException

logger = logging.getLogger(__name__)


class MongoDynamicConnection:
    """
    Dynamic MongoDB connection manager.
    Provides methods to access different MongoDB databases dynamically.
    """

    def __init__(self, default_mongo_db: AsyncIOMotorDatabase):
        """
        Initialize with a default MongoDB database.

        Args:
            default_mongo_db: The default MongoDB database instance
        """
        self.default_mongo_db = default_mongo_db

    async def get_db(self, db_name: str = None) -> AsyncIOMotorDatabase:
        """
        Get MongoDB database dynamically. If no db_name provided, use default.

        Args:
            db_name: Name of the database to access. If None, returns default database.

        Returns:
            AsyncIOMotorDatabase: The requested database instance

        Raises:
            CustomErrorException: If database access fails
        """
        try:
            if db_name:
                # Use the same MongoDB client but access a different database
                client = self.default_mongo_db.client
                logger.info(f"Accessing MongoDB database: {db_name}")
                return client[db_name]

            logger.info("Using default MongoDB database")
            return self.default_mongo_db

        except Exception as e:
            logger.error(f"Failed to get MongoDB database '{db_name}': {e}")
            raise CustomErrorException(
                f"Failed to get MongoDB database: {e}", status_code=500) from e

    async def list_databases(self) -> list:
        """
        List all available databases.

        Returns:
            list: List of database names

        Raises:
            CustomErrorException: If listing databases fails
        """
        try:
            client = self.default_mongo_db.client
            database_list = await client.list_database_names()
            logger.info(f"Available databases: {database_list}")
            return database_list

        except Exception as e:
            logger.error(f"Failed to list databases: {e}")
            raise CustomErrorException(
                f"Failed to list databases: {e}", status_code=500) from e

    async def database_exists(self, db_name: str) -> bool:
        """
        Check if a database exists.

        Args:
            db_name: Name of the database to check

        Returns:
            bool: True if database exists, False otherwise

        Raises:
            CustomErrorException: If check fails
        """
        try:
            databases = await self.list_databases()
            exists = db_name in databases
            logger.info(f"Database '{db_name}' exists: {exists}")
            return exists

        except Exception as e:
            logger.error(
                f"Failed to check if database '{db_name}' exists: {e}")
            raise CustomErrorException(
                f"Failed to check database existence: {e}", status_code=500) from e


# Factory function to create MongoDB dynamic connection
def create_mongo_dynamic_connection(default_mongo_db: AsyncIOMotorDatabase) -> MongoDynamicConnection:
    """
    Factory function to create a MongoDB dynamic connection instance.

    Args:
        default_mongo_db: The default MongoDB database instance

    Returns:
        MongoDynamicConnection: Configured MongoDB dynamic connection instance
    """
    return MongoDynamicConnection(default_mongo_db)
