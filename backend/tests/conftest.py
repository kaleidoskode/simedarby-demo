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
from redis.asyncio import Redis

from app.databases.redis.config import Config
from app.seed.seeder import demo_showtime_id

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
API = f"{BASE_URL}/api/v1"


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


@pytest_asyncio.fixture(autouse=True)
async def clean_locks(redis):
    """Clear every seat lock before and after each test.

    Without this a lock left by one test would make the next one fail for the
    wrong reason, and the TTL is long enough that tests cannot wait it out.
    """
    async def purge():
        keys = [key async for key in redis.scan_iter(match="lock:*", count=500)]
        if keys:
            await redis.delete(*keys)

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
