
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from app.databases.mysql.config import Config  # Import the configuration class


class Database:
    """A class to handle multiple database connections.

    Engines are created on first use rather than at import time. The module
    level `db_instance` below is imported transitively by anything that touches
    the databases package, and connecting eagerly meant a deployment without
    MySQL credentials could not start at all.
    """

    def __init__(self):
        self.engines = {}
        self._sessions = {}
        self._initialised = False

    def _initialise(self):
        """Create an engine and session factory per configured database."""
        if self._initialised:
            return

        # Retrieve connection configurations
        connection_configs = Config.databases()

        # Initialize each connection
        for name, url in connection_configs.items():
            self.engines[name] = self.create_engine(url)
            self._sessions[name] = self.create_session(self.engines[name])

        self._initialised = True

    @property
    def sessions(self):
        """Session factories keyed by database name, built on first access."""
        self._initialise()
        return self._sessions

    def create_engine(self, url):
        """
        Create and return a SQLAlchemy engine with optimized connection pooling.

        Pool settings are optimized for MySQL and provide:
        - Connection reuse for better performance
        - Automatic connection validation
        - Proper connection lifecycle management
        """
        # Determine environment for pool sizing
        system_env = os.getenv('SYSTEM_ENV', 'development')
        is_production = system_env == 'production'

        # Pool configuration based on environment
        pool_config = {
            'poolclass': QueuePool,
            'pool_size': 20 if is_production else 5,  # More connections for prod
            'max_overflow': 30 if is_production else 10,  # Allow overflow connections
            'pool_timeout': 30,  # Wait up to 30 seconds for connection
            # Recycle connections every hour (MySQL 8-hour limit)
            'pool_recycle': 3600,
            'pool_pre_ping': True,  # Test connections before use
            'echo': not is_production,  # SQL logging only in development
        }

        # MySQL-specific connection arguments
        connect_args = {
            'connect_timeout': 10,  # Connection timeout
            'read_timeout': 30,    # Read timeout
            'write_timeout': 30,   # Write timeout
            'autocommit': False,   # Explicit transaction management
        }

        return create_engine(
            url,
            **pool_config,
            connect_args=connect_args
        )

    def create_session(self, engine):
        """Create and return a session bound to a given engine."""
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Base class for declarative models
Base = declarative_base()

# Instantiate the database to expose engines and sessions
db_instance = Database()

# Usage examples:
# Access engines: db_instance.engines["database_name"]
# Access sessions: db_instance.sessions["database_name"]()
# Example: engine = db_instance.engines["password_management"]
# Example: SessionLocal = db_instance.sessions["password_management"]
