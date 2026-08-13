"""Shared test fixtures.

The suite runs against the live stack over HTTP rather than in process. That is
deliberate: gunicorn serves these requests from several worker processes, so a
lock that held only within one event loop would fail here. Testing through the
socket is what proves the guarantee survives horizontal scaling, which is the
whole reason the lock lives in Redis rather than in memory.

Run with:  docker compose exec api pytest -v
"""

import os
from datetime import datetime, timezone
from typing import List

import httpx
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from app.databases.mongodb import collections
from app.databases.mongodb.config import Config as MongoConfig
from app.databases.redis.config import Config
from app.seed.seeder import demo_showtime_id

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
API = f"{BASE_URL}/api/v1"

# The booking that owns the wireframe's crossed-out seats. It is part of the
# seeded fixture, so cleanup between tests must leave it alone.
SEEDED_BOOKING_ID = "bkg_seeded_taken"


@pytest_asyncio.fixture
async def api():
    """HTTP client pointed at the running API."""
    async with httpx.AsyncClient(base_url=API, timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture
async def redis():
    """Direct Redis access, for asserting on lock keys and TTLs."""
    client = Redis.from_url(Config.set_redis(), decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def showtime_id(api) -> str:
    """The screening from the wireframe.

    This one specifically, rather than whichever comes first, because it is the
    only seeded screening carrying pre-sold seats. Tests that need a booked
    seat would otherwise be skipped, and a skipped test proves nothing.
    """
    wanted = demo_showtime_id()

    response = await api.get("/showtimes", params={"limit": 500})
    response.raise_for_status()
    showtimes = {s["id"]: s for s in response.json()["data"]}
    assert wanted in showtimes, (
        f"Demo screening {wanted} not found. Run: python -m app.seed --reset")

    starts_at = datetime.fromisoformat(showtimes[wanted]["starts_at"])
    assert starts_at > datetime.now(timezone.utc), (
        "Demo screening is in the past. Run: python -m app.seed --reset")
    return wanted


@pytest_asyncio.fixture
async def mongo():
    """Direct MongoDB access, for undoing what a test wrote."""
    database = os.environ["MONGO1_DB"]
    client = AsyncIOMotorClient(MongoConfig.set_mongo(database), tz_aware=True)
    yield client[database]
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_state(redis, mongo):
    """Return the database and Redis to their seeded state around each test.

    Locks are cleared because one left behind makes the next test fail for the
    wrong reason, and the TTL is too long to wait out.

    Bookings and reservations are cleared because paying writes a *permanent*
    seat reservation. Without this the suite consumes seats on every run and
    eventually fails when the hall is full — passing on a fresh database and
    failing on the second run, which is worse than failing outright.

    The seeded booking is kept, since the crossed-out seats from the wireframe
    are part of the fixture rather than test output.
    """
    async def purge():
        keys = [key async for key in redis.scan_iter(match="lock:*", count=500)]
        if keys:
            await redis.delete(*keys)

        await mongo[collections.BOOKINGS].delete_many(
            {"_id": {"$ne": SEEDED_BOOKING_ID}})
        await mongo[collections.SEAT_RESERVATIONS].delete_many(
            {"booking_id": {"$ne": SEEDED_BOOKING_ID}})

    await purge()
    yield
    await purge()


@pytest_asyncio.fixture
async def token(api):
    """Factory issuing a fresh guest identity per call."""
    async def _token(name: str = "Tester") -> str:
        response = await api.post("/auth/token", json={"name": name})
        response.raise_for_status()
        return response.json()["data"]["access_token"]

    return _token


@pytest.fixture
def auth_header():
    """Build an Authorization header from a token."""
    def _header(access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}

    return _header


@pytest_asyncio.fixture
async def free_seats(api, showtime_id) -> List[str]:
    """Seats that are currently available on the demo screening."""
    response = await api.get(f"/showtimes/{showtime_id}/seats")
    response.raise_for_status()
    plan = response.json()["data"]
    return [
        seat["seat"]
        for row in plan["rows"]
        for seat in row["seats"]
        if seat["status"] == "available"
    ]
