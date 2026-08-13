"""Dependency injection for the service layer.

Each service is constructed here and injected into routes with `Depends(...)`,
so routes stay free of datastore wiring and a service can be swapped in tests
by overriding a single dependency.
"""

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.databases.mongodb.dependencies import get_mongo_db1
from app.services import auth_services, catalog_services


async def auth() -> auth_services.AuthServices:
    """Token issuing. Holds no state and needs no datastore."""
    return auth_services.AuthServices()


async def catalog(
    mongo_db1: AsyncIOMotorDatabase = Depends(get_mongo_db1),
) -> catalog_services.CatalogServices:
    """Read side: movies, reviews, venues, screenings and food."""
    return catalog_services.CatalogServices(mongo_db1)
