import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.databases.mongodb.db import MongoService

load_dotenv()

# Instantiate the MongoService
mongo_service = MongoService()


async def get_mongo_db1() -> AsyncIOMotorDatabase:
    """Return the appropriate MongoDB database instance."""
    return await mongo_service.get_database(f"{os.getenv('MONGO1_DB')}")
