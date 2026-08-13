"""WebSocket fan-out for the seating plan.

The naive design gives every connected client its own blocking read on Redis.
With 300 people looking at one popular screening that is 300 Redis connections
carrying identical data.

Instead each worker process keeps **one** reader per showtime, and fans what it
reads out to the sockets it is serving locally:

    Redis stream ──XREAD BLOCK──> reader task (one per worker per showtime)
                                        │
                            ┌───────────┼───────────┐
                            ▼           ▼           ▼
                         socket      socket      socket

Redis connections then scale with the number of screenings being watched per
worker, not with the number of viewers. The reader starts when the first client
subscribes and stops when the last one leaves.

Because the log lives in Redis and not in this process, a client can reconnect
to any worker and catch up with `?since=`. Nothing here is authoritative; it is
purely a delivery mechanism over the same stream the polling endpoint reads.
"""

import asyncio
import logging
from typing import Dict, List, Set, Tuple

from fastapi import WebSocket

from app.databases.redis.dependencies import redis_service
from app.services.event_services import EventServices

logger = logging.getLogger(__name__)

# How long a reader waits on Redis before looping. It is not a delay on
# delivery: XREAD returns the moment an entry arrives. The timeout only decides
# how often an idle reader wakes to check whether it should stop.
_BLOCK_MS = 5000


class ShowtimeBroadcaster:
    """Per worker registry of seating plan subscribers."""

    def __init__(self):
        # showtime_id -> {(websocket, viewer_id)}
        self._subscribers: Dict[str, Set[Tuple[WebSocket, str]]] = {}
        self._readers: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    def viewer_count(self, showtime_id: str) -> int:
        return len(self._subscribers.get(showtime_id, ()))

    async def subscribe(self, showtime_id: str, websocket: WebSocket,
                        viewer_id: str, from_version: str) -> None:
        """Register a socket, starting the reader if it is the first."""
        async with self._lock:
            subscribers = self._subscribers.setdefault(showtime_id, set())
            subscribers.add((websocket, viewer_id))

            if showtime_id not in self._readers:
                self._readers[showtime_id] = asyncio.create_task(
                    self._read_stream(showtime_id, from_version),
                    name=f"seat-reader:{showtime_id}")
                logger.info("Started seat stream reader for %s", showtime_id)

    async def unsubscribe(self, showtime_id: str, websocket: WebSocket,
                          viewer_id: str) -> None:
        """Remove a socket, stopping the reader once nobody is left."""
        async with self._lock:
            subscribers = self._subscribers.get(showtime_id, set())
            subscribers.discard((websocket, viewer_id))

            if not subscribers:
                self._subscribers.pop(showtime_id, None)
                reader = self._readers.pop(showtime_id, None)
                if reader:
                    reader.cancel()
                    logger.info("Stopped seat stream reader for %s",
                                showtime_id)

    async def _read_stream(self, showtime_id: str, from_version: str) -> None:
        """Follow the Redis stream and fan each entry out to local sockets."""
        redis = await redis_service.get_client()
        events = EventServices(redis)
        key = events.stream_key(showtime_id)
        last_id = from_version or "0-0"

        try:
            while True:
                entries = await redis.xread({key: last_id}, block=_BLOCK_MS,
                                            count=100)
                if not entries:
                    continue  # idle timeout, loop and wait again

                for _, records in entries:
                    for entry_id, fields in records:
                        last_id = entry_id
                        await self._fan_out(showtime_id, entry_id, fields)

        except asyncio.CancelledError:
            raise
        except Exception:
            # A reader dying must not take the process with it. The sockets
            # stay open and clients can fall back to polling with ?since=.
            logger.exception("Seat stream reader failed for %s", showtime_id)

    async def _fan_out(self, showtime_id: str, entry_id: str,
                       fields: Dict[str, str]) -> None:
        """Deliver one seat change, personalised per recipient."""
        subscribers = list(self._subscribers.get(showtime_id, ()))
        if not subscribers:
            return

        holder = fields.get("holder") or ""
        dead: List[Tuple[WebSocket, str]] = []

        for websocket, viewer_id in subscribers:
            # held_by_me is resolved per socket so the holder's id never
            # travels to anyone else.
            payload = {
                "type": "seat_change",
                "version": entry_id,
                "changes": [{
                    "seat": fields.get("seat"),
                    "status": fields.get("status"),
                    "held_by_me": bool(viewer_id) and holder == viewer_id,
                    "at": fields.get("at"),
                }],
            }
            try:
                await websocket.send_json(payload)
            except Exception:
                # Client vanished mid-send; clean it up after the loop.
                dead.append((websocket, viewer_id))

        for websocket, viewer_id in dead:
            await self.unsubscribe(showtime_id, websocket, viewer_id)

    async def close(self) -> None:
        """Cancel every reader, for a clean shutdown."""
        async with self._lock:
            for showtime_id, reader in self._readers.items():
                reader.cancel()
                logger.info("Cancelled seat stream reader for %s", showtime_id)
            self._readers.clear()
            self._subscribers.clear()


# One per worker process. Subscribers are local to the worker; the log they all
# read is shared, which is what lets any worker serve any client.
broadcaster = ShowtimeBroadcaster()
