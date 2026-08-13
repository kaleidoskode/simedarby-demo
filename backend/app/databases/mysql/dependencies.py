from typing import Generator, Callable
from sqlalchemy.orm import Session
import logging

from app.databases.mysql.db import db_instance

# Configure logging for database operations
logger = logging.getLogger(__name__)


def get_session_factory(database_name: str) -> Callable:
    """
    Get a database session factory for the specified database name.

    Args:
        database_name: Name of the database as configured in settings

    Returns:
        SQLAlchemy sessionmaker factory function

    Raises:
        KeyError: If database_name is not configured
        RuntimeError: If database instance is not properly initialized
    """
    if not hasattr(db_instance, 'sessions'):
        raise RuntimeError("Database instance not properly initialized")

    if database_name not in db_instance.sessions:
        available_dbs = list(db_instance.sessions.keys())
        raise KeyError(
            f"Database '{database_name}' not found. Available databases: {available_dbs}"
        )

    logger.debug(f"Retrieved session factory for database: {database_name}")
    return db_instance.sessions[database_name]


def get_database_session(database_name: str) -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions with automatic cleanup.

    This function provides a SQLAlchemy session for the specified database
    and ensures proper cleanup after the request completes.

    Args:
        database_name: Name of the database to connect to

    Yields:
        SQLAlchemy Session object for database operations

    Example:
        @app.get("/items")
        def read_items(db: Session = Depends(get_database_session)):
            return db.query(Item).all()
    """
    session_factory = get_session_factory(database_name)
    db_session = session_factory()

    logger.debug(f"Created database session for: {database_name}")

    try:
        yield db_session
    except Exception as e:
        logger.error(f"Database session error for {database_name}: {e}")
        db_session.rollback()
        raise
    finally:
        db_session.close()
        logger.debug(f"Closed database session for: {database_name}")


# Legacy function for backward compatibility
def get_mysql_db1() -> Generator[Session, None, None]:
    yield from get_database_session("password_management")
