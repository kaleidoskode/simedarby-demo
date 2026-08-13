import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.databases.mongodb.config import Config

logger = logging.getLogger(__name__)



class MongoService:
    """Service for managing MongoDB connections."""
    
    def __init__(self):
        """Initialize the service with empty client and database containers."""
        self.clients = {}  # Stores MongoDB clients
        self.dbs = {}      # Stores MongoDB database instances
    
    def connect(self, db_name: str) -> AsyncIOMotorDatabase:
        """Establish and return a connection to the specified MongoDB database."""

        # If the database connection already exists, reuse it
        if db_name in self.dbs:
            return self.dbs[db_name]

        database_url = Config.set_mongo(db_name)

        # tz_aware makes the driver return timezone aware datetimes rather than
        # naive ones. Without it a screening serialises as
        # "2026-08-14T01:20:00" with no designator, and a client would read that
        # as local time and show the wrong screening.
        client = AsyncIOMotorClient(database_url, tz_aware=True)
        logger.info("Connected to MongoDB database: %s", db_name)

        # Store the client and the connected database
        self.clients[db_name] = client
        self.dbs[db_name] = client[db_name]

        return self.dbs[db_name]

    async def get_database(self, db_name: str) -> AsyncIOMotorDatabase:
        """Return the MongoDB database instance for the specified name."""
        return self.connect(db_name)

    def close(self):
        """Close every open client and forget the cached databases."""
        for client in self.clients.values():
            client.close()
        self.clients.clear()
        self.dbs.clear()
