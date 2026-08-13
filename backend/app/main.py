from contextlib import asynccontextmanager
from dotenv import load_dotenv
from app.middleware.exception import ExceptionHandler
from app.middleware import process_time_log
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.databases.mongodb.dependencies import get_mongo_db1, mongo_service
from app.databases.redis.dependencies import get_redis, redis_service
from fastapi import FastAPI, Request, HTTPException
import asyncio
import logging
import uvicorn
from typing import Any, Callable, TypeVar
import os


load_dotenv()

logger = logging.getLogger(__name__)


description = """
Backend API for the Cinema Booking App.

The booking flow is **first come first serve**: a seat is held the moment a
user selects it, and every other user watching that seating plan is told
immediately.

* **Seat locks** live in Redis as keys with a TTL, so an abandoned app frees
  its seats without any sweeper job.
* **Double booking** is prevented by a unique index in MongoDB, not by the
  lock alone, so the guarantee survives a Redis restart.
* **Real-time updates** are published to a Redis stream, which both the
  WebSocket and the polling endpoint read, so the two transports can never
  disagree.
* **Statelessness**: no session is held server side. Callers carry a JWT and
  all shared state lives in Redis and MongoDB, so any worker can serve any
  request.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the datastore connections on boot and release them on shutdown."""
    try:
        await get_mongo_db1()
        await get_redis()
    except Exception as exc:
        # Surface the cause instead of failing later on the first request.
        logger.error("Startup connection failure: %s", exc, exc_info=True)
        raise

    yield

    await redis_service.close()
    mongo_service.close()


app = FastAPI(
    title=settings.title,
    description=description,
    version=settings.version,
    docs_url="/docs",
    openapi_url="/openapi.json",
    root_path=settings.root_path,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origins=["*"],
)
app.middleware("http")(process_time_log.log)
app.add_middleware(ExceptionHandler)


@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    # WebSocket traffic never reaches HTTP middleware, so a long lived seating
    # plan subscription is not affected by this timeout.
    try:
        return await asyncio.wait_for(call_next(request), timeout=600)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Request timeout")


F = TypeVar("F", bound=Callable[..., Any])


@app.get("/health", tags=["health"])
async def health_check():
    """Report service status along with the reachability of each datastore."""
    dependencies = {}

    try:
        mongo_db = await get_mongo_db1()
        await mongo_db.command("ping")
        dependencies["mongodb"] = "up"
    except Exception as exc:
        logger.error("MongoDB health check failed: %s", exc)
        dependencies["mongodb"] = "down"

    try:
        redis_client = await get_redis()
        await redis_client.ping()
        dependencies["redis"] = "up"
    except Exception as exc:
        logger.error("Redis health check failed: %s", exc)
        dependencies["redis"] = "down"

    healthy = all(state == "up" for state in dependencies.values())

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "healthy" if healthy else "degraded",
            "service": "cinema-booking-api",
            "version": settings.version,
            "dependencies": dependencies,
        },
    )


# Routers are registered here as each phase lands:
#   /api/v1/auth, /api/v1/movies, /api/v1/showtimes,
#   /api/v1/fnb, /api/v1/bookings, /api/v1/ws

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 20015)),
        log_level="debug",
        reload=True,
    )
