"""Dependency injection for the service layer.

Each service is constructed here and injected into routes with `Depends(...)`,
so routes stay free of datastore wiring and a service can be swapped in tests
by overriding a single dependency.
"""

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.databases.mongodb.dependencies import get_mongo_db1
from app.databases.redis.dependencies import get_redis
from app.services import (
    auth_services,
    catalog_services,
    event_services,
    lock_services,
    seat_services,
)


async def auth() -> auth_services.AuthServices:
    """Token issuing. Holds no state and needs no datastore."""
    return auth_services.AuthServices()


async def catalog(
    mongo_db1: AsyncIOMotorDatabase = Depends(get_mongo_db1),
) -> catalog_services.CatalogServices:
    """Read side: movies, reviews, venues, screenings and food."""
    return catalog_services.CatalogServices(mongo_db1)


async def locks(
    redis: Redis = Depends(get_redis),
) -> lock_services.LockServices:
    """Redis seat locks."""
    return lock_services.LockServices(redis)


async def events(
    redis: Redis = Depends(get_redis),
) -> event_services.EventServices:
    """The per showtime seat change stream."""
    return event_services.EventServices(redis)


async def seats(
    mongo_db1: AsyncIOMotorDatabase = Depends(get_mongo_db1),
    lock: lock_services.LockServices = Depends(locks),
    event: event_services.EventServices = Depends(events),
) -> seat_services.SeatServices:
    """The seating plan, combining the layout, reservations and locks."""
    return seat_services.SeatServices(mongo_db1, lock, event)
