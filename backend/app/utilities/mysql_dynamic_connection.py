"""
Dynamic Database Connection Manager
Equivalent to Node.js connection pattern with caching, pooling, and health checks.
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError
from cachetools import TTLCache
import threading
from contextlib import contextmanager

from app.utilities.prefered_environment import environment
from app.middleware.exception import CustomErrorException

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Dynamic database connection manager with caching and health checks.
    Similar to Node.js Sequelize connection pattern.
    """

    def __init__(self):
        # Connection cache with TTL (2 minutes like Node.js version)
        self.connection_cache = TTLCache(maxsize=100, ttl=120)  # 2 minutes
        self.connection_locks = {}
        self.lock = threading.Lock()

        # Background cleanup task
        self._cleanup_interval = 60  # 1 minute health check
        self._cleanup_task = None
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        """Start background cleanup task for connection health checks."""
        def cleanup_loop():
            while True:
                try:
                    asyncio.run(self._health_check_all_connections())
                    threading.Event().wait(self._cleanup_interval)
                except Exception as e:
                    logger.error(f"Health check error: {e}")

        if not self._cleanup_task or not self._cleanup_task.is_alive():
            self._cleanup_task = threading.Thread(
                target=cleanup_loop, daemon=True)
            self._cleanup_task.start()

    def _get_connection_key(self, credentials: Dict[str, Any], select_db: str) -> str:
        """Generate unique key per DB connection."""
        host = credentials.get('host', 'localhost')
        db_name = credentials.get(select_db, 'default')
        return f"{host}:3306/{db_name}"

    async def _validate_connection(self, engine) -> bool:
        """Ping to check if connection is still alive."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False

    async def _health_check_all_connections(self):
        """Background health check for all cached connections."""
        with self.lock:
            dead_keys = []
            for key, cached_data in list(self.connection_cache.items()):
                try:
                    if not await self._validate_connection(cached_data['engine']):
                        logger.warning(
                            f"Connection {key} is dead. Cleaning up.")
                        dead_keys.append(key)
                except Exception as e:
                    logger.error(f"Health check error for {key}: {e}")
                    dead_keys.append(key)

            # Clean up dead connections
            for key in dead_keys:
                await self._cleanup_connection(key)

    async def _cleanup_connection(self, connection_key: str):
        """Clean up a specific connection."""
        try:
            if connection_key in self.connection_cache:
                cached_data = self.connection_cache[connection_key]
                engine = cached_data['engine']

                # Close the engine
                if hasattr(engine, 'dispose'):
                    engine.dispose()

                # Remove from cache
                del self.connection_cache[connection_key]
                logger.info(f"Cleaned up connection: {connection_key}")
        except Exception as e:
            logger.warning(f"Error during cleanup of {connection_key}: {e}")

    def _get_db_credentials(self, env: str = None, connection_credentials: Dict[str, Any] = None) -> Dict[str, str]:
        """Get database credentials from environment variables and connection credentials."""
        if not env:
            env = os.getenv("SYSTEM_ENV", "local")

        try:
            creds = environment(env, "mysql1")

            # Use dynamic values from connection_credentials if provided
            if connection_credentials:
                creds['db'] = connection_credentials.get(
                    'db_name', creds.get('db'))
                creds['host'] = connection_credentials.get(
                    'host', creds.get('host'))

            return creds
        except Exception as e:
            logger.error(f"Failed to get DB credentials: {e}")
            raise CustomErrorException(
                f"Database credential error: {e}", status_code=500)

    def _create_engine(self, credentials: Dict[str, Any], select_db: str):
        """Create SQLAlchemy engine with connection pooling."""
        db_creds = self._get_db_credentials(connection_credentials=credentials)

        # Get database name from credentials
        database_name = credentials.get(select_db)
        if not database_name:
            raise CustomErrorException(
                f"Database name not found for {select_db}", status_code=400)

        # Use host from credentials, but username/password from environment
        host = credentials.get('host', 'localhost')
        username = db_creds['username']
        password = db_creds['password']

        # Create connection URL
        database_url = f"mysql+pymysql://{username}:{password}@{host}:3306/{database_name}"

        # SQLAlchemy engine options (similar to Sequelize options)
        engine = create_engine(
            database_url,
            pool_size=20,           # max connections
            max_overflow=0,         # additional connections beyond pool_size
            pool_pre_ping=True,     # validate connections before use
            pool_recycle=3600,      # recycle connections after 1 hour
            pool_timeout=30,        # timeout for getting connection from pool
            echo=False,             # set to True for SQL logging
            connect_args={
                "connect_timeout": 30,
                "charset": "utf8mb4",
            }
        )

        return engine

    async def get_connection(
        self,
        connection_credentials: Dict[str, Any],
        preferred_db: int = 1
    ) -> Tuple[Session, callable]:
        """
        Main function to get database connection with caching.

        Args:
            connection_credentials: Dict containing host, db_name, etc.
            preferred_db: 1 for db_name, 2 for db_name2

        Returns:
            Tuple of (Session, cleanup_function)
        """
        select_db = "db_name" if preferred_db == 1 else "db_name2"
        connection_key = self._get_connection_key(
            connection_credentials, select_db)

        # Check if cached connection is valid
        with self.lock:
            if connection_key in self.connection_cache:
                cached_data = self.connection_cache[connection_key]
                if await self._validate_connection(cached_data['engine']):
                    logger.info(
                        f"Reusing cached connection for {connection_key}")

                    # Create new session from cached engine
                    SessionLocal = sessionmaker(bind=cached_data['engine'])
                    session = SessionLocal()

                    def cleanup():
                        try:
                            session.close()
                        except Exception as e:
                            logger.warning(f"Session cleanup error: {e}")

                    return session, cleanup
                else:
                    # Connection is dead, remove from cache
                    await self._cleanup_connection(connection_key)

        # Prevent concurrent creation of the same connection
        if connection_key in self.connection_locks:
            logger.info(f"Waiting for lock: {connection_key}")
            return await self.connection_locks[connection_key]

        # Create the connection
        async def create_connection():
            try:
                logger.info(f"Creating new connection for {connection_key}")

                # Create engine
                engine = self._create_engine(connection_credentials, select_db)

                # Test the connection
                await self._validate_connection(engine)
                logger.info(f"Connected to {connection_key}")

                # Store in cache
                with self.lock:
                    self.connection_cache[connection_key] = {
                        'engine': engine,
                        'created_at': datetime.now(),
                    }

                # Create session
                SessionLocal = sessionmaker(bind=engine)
                session = SessionLocal()

                def cleanup():
                    try:
                        session.close()
                    except Exception as e:
                        logger.warning(f"Session cleanup error: {e}")

                return session, cleanup

            except Exception as e:
                logger.error(f"Connection error for {connection_key}: {e}")
                raise CustomErrorException(
                    f"Database connection error: {e}", status_code=500)
            finally:
                # Always release lock
                if connection_key in self.connection_locks:
                    del self.connection_locks[connection_key]

        # Set lock and create connection
        connection_promise = create_connection()
        self.connection_locks[connection_key] = connection_promise

        return await connection_promise

    @contextmanager
    def get_sync_connection(
        self,
        connection_credentials: Dict[str, Any],
        preferred_db: int = 1
    ):
        """
        Synchronous version of get_connection for use in sync contexts.

        Usage:
            with connection_manager.get_sync_connection(credentials) as session:
                result = session.execute(text("SELECT * FROM users"))
        """
        select_db = "db_name" if preferred_db == 1 else "db_name2"
        connection_key = self._get_connection_key(
            connection_credentials, select_db)

        try:
            # Create engine if not cached
            with self.lock:
                if connection_key not in self.connection_cache:
                    engine = self._create_engine(
                        connection_credentials, select_db)
                    self.connection_cache[connection_key] = {
                        'engine': engine,
                        'created_at': datetime.now(),
                    }
                else:
                    engine = self.connection_cache[connection_key]['engine']

            # Create session
            SessionLocal = sessionmaker(bind=engine)
            session = SessionLocal()

            yield session

        except Exception as e:
            logger.error(f"Sync connection error for {connection_key}: {e}")
            raise CustomErrorException(
                f"Database connection error: {e}", status_code=500)
        finally:
            try:
                session.close()
            except Exception as e:
                logger.warning(f"Session cleanup error: {e}")

    async def close_all_connections(self):
        """Close all cached connections."""
        with self.lock:
            for key in list(self.connection_cache.keys()):
                await self._cleanup_connection(key)
        logger.info("All connections closed")


# Global connection manager instance
connection_manager = ConnectionManager()


async def create_mysql_dynamic_connection(credential_info: dict, preferred_db: int = 1):
    """
    Get a dynamic MySQL connection using the connection manager.

    Args:
        credential_info: Dict containing host, db_name, etc. from JWT
        preferred_db: 1 for db_name, 2 for db_name2

    Returns:
        Tuple of (session, cleanup_function)

    Example:
        session, cleanup = await self.get_dynamic_mysql_connection(credential_info)
        try:
            result = session.execute(text("SELECT * FROM users LIMIT 10"))
            users = result.fetchall()
        finally:
            cleanup()
    """
    try:
        return await connection_manager.get_connection(
            connection_credentials=credential_info,
            preferred_db=preferred_db
        )
    except Exception as e:
        raise CustomErrorException(
            f"Failed to establish dynamic database connection: {e}", status_code=500) from e
