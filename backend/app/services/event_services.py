"""Seat change events, published to a Redis stream.

A stream rather than pub/sub, deliberately. Pub/sub is fire and forget: a
subscriber that reconnects has no way to learn what it missed, and a polling
endpoint could not be built on it at all. Every stream entry has an id, so the
same log serves the WebSocket, the polling fallback and reconnect catch-up, and
those three can never disagree about what happened.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from redis.asyncio import Redis
from redis.exceptions import ResponseError

logger = logging.getLogger(__name__)

# Entries older than this are trimmed. A seating plan is only open for minutes,
# so this is far more history than any client needs to catch up.
STREAM_MAXLEN = 1000


class HistoryUnavailable(Exception):
    """The position asked for is older than the entries still retained.

    Raised rather than returning what happens to have survived: a partial
    answer would leave the client believing it had caught up while quietly
    missing every change that was trimmed.
    """

    def __init__(self, since: str, oldest: str):
        self.since = since
        self.oldest = oldest
        super().__init__(
            f"Version '{since}' is older than the retained log, "
            f"which starts at '{oldest}'")


def _position(entry_id: str) -> Optional[Tuple[int, int]]:
    """Parse a stream id into a comparable `(ms, seq)` pair.

    Returns None when it is not one, leaving Redis to reject the id so that a
    malformed version keeps producing the same error it always did.
    """
    milliseconds, _, sequence = entry_id.partition("-")
    try:
        return int(milliseconds), int(sequence or 0)
    except ValueError:
        return None


class EventServices:
    """Publishes and reads the per showtime seat change log."""

    def __init__(self, redis: Redis):
        self.redis = redis

    @staticmethod
    def stream_key(showtime_id: str) -> str:
        return f"stream:showtime:{showtime_id}"

    async def publish(self, showtime_id: str,
                      changes: List[Dict[str, Any]]) -> Optional[str]:
        """Append seat changes, returning the id of the last entry written.

        Each change is one seat, so a client can apply them individually
        without re-fetching the whole plan.
        """
        if not changes:
            return None

        key = self.stream_key(showtime_id)
        now = datetime.now(timezone.utc).isoformat()
        last_id = None

        pipe = self.redis.pipeline()
        for change in changes:
            pipe.xadd(
                key,
                {
                    "seat": change["seat"],
                    "status": change["status"],
                    # An empty string rather than a missing field: Redis stream
                    # values must be strings, and a consistent shape keeps the
                    # consumer free of key existence checks.
                    "holder": change.get("holder") or "",
                    "at": now,
                },
                maxlen=STREAM_MAXLEN,
                approximate=True,
            )
        results = await pipe.execute()
        if results:
            last_id = results[-1]

        logger.debug("Published %d seat changes to %s", len(changes), key)
        return last_id

    async def latest_version(self, showtime_id: str) -> str:
        """The newest entry id, or "0-0" when nothing has happened yet.

        Clients pass this back as `?since=` to receive only later changes.
        """
        entries = await self.redis.xrevrange(
            self.stream_key(showtime_id), count=1)
        return entries[0][0] if entries else "0-0"

    async def covers(self, showtime_id: str, since: str) -> bool:
        """Whether every entry after `since` is still in the stream.

        Trimming only ever removes from the head, so the log still covers a
        position in two cases: nothing has been trimmed at all, or the position
        is at or after the oldest entry that survived. Sitting exactly on that
        oldest entry is covered — everything after it is by definition intact.
        """
        try:
            info = await self.redis.xinfo_stream(self.stream_key(showtime_id))
        except ResponseError:
            # No stream yet, so nothing has happened and nothing is missing.
            return True

        # `entries-added` counts every append ever made. While it matches the
        # current length nothing has been trimmed, so any position is covered.
        # This is what stops a client sitting at "0-0" being sent to refetch on
        # the first change to a quiet screening.
        if info.get("entries-added") == info["length"]:
            return True

        oldest = info.get("recorded-first-entry-id")
        if oldest is None:
            entry = info.get("first-entry")
            oldest = entry[0] if entry else None
        if not oldest or oldest == "0-0":
            # Trimmed empty: there is no surviving entry to resume from.
            return False

        if since in ("", "0-0"):
            # Asking from the beginning of the log, and the beginning is gone.
            return False

        position, first = _position(since), _position(oldest)
        if position is None or first is None:
            return True
        return position >= first

    async def read_since(self, showtime_id: str, since: str,
                         limit: int = 500) -> List[Dict[str, Any]]:
        """Replay entries recorded after `since`.

        This is what a stream buys over pub/sub. A subscriber that dropped its
        connection, or a client polling on an interval, can ask for exactly
        what it missed instead of re-fetching the entire seating plan.

        Raises `HistoryUnavailable` when the position has been trimmed away,
        because the alternative — returning the surviving tail — is a silent
        gap in the client's seat state rather than a visible failure.
        """
        if not await self.covers(showtime_id, since):
            info = await self.redis.xinfo_stream(self.stream_key(showtime_id))
            raise HistoryUnavailable(
                since, info.get("recorded-first-entry-id") or "0-0")

        # The bracket makes the range exclusive, so the caller does not receive
        # the entry it already has.
        start = f"({since}" if since and since != "0-0" else "-"

        try:
            entries = await self.redis.xrange(
                self.stream_key(showtime_id), min=start, max="+", count=limit)
        except Exception as exc:
            # A malformed id from a client should be a bad request, not a 500.
            raise ValueError(f"Invalid version '{since}'") from exc

        return [
            {"id": entry_id, **fields}
            for entry_id, fields in entries
        ]
