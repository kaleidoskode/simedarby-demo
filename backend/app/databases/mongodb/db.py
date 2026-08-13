from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.databases.mongodb.config import Config



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
        
        # Determine if we're in testing mode
        if Config.set_testing():
            from mongomock_motor import AsyncMongoMockClient
            client = AsyncMongoMockClient()
            print(f"Using mock MongoDB client for '{db_name}'")
        else:
            # Get the MongoDB URL for the given database
            database_url = Config.set_mongo(db_name)
            client = AsyncIOMotorClient(database_url)
            print(f"Connected to MongoDB database: {db_name}")
        
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
