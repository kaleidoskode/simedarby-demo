"""Seat locks in Redis.

This is the "first come first serve" mechanism. A lock is a key per seat,
carrying the holder's user id and a TTL:

    lock:{showtime_id}:{seat} -> "usr_8f2a7c1e"   PX 120000

Three properties make it correct, and each comes from the same place — the
operations are Lua scripts, and Redis runs a script to completion before any
other command:

* **Nothing interleaves.** Checking every requested seat and then claiming them
  happens as one indivisible step, so two users racing for the same seat cannot
  both observe it free.
* **All or nothing.** A request for F4 and F5 either takes both or takes
  neither, so a user never ends up holding half a selection. Doing this with
  SET NX per seat would need rollback logic, and a crash mid-rollback would
  leak a lock.
* **Only the holder may release or extend.** The compare and delete is inside
  the script, so User 2 cannot free User 1's seat between the read and the
  write.

The TTL is what makes an abandoned app harmless: close it on the seating plan
and the seats free themselves. No sweeper job, no expiry table, nothing to run
on a schedule.

Redis is not the final authority. It stops two users reaching checkout for the
same seat, but a lock can be lost to a restart or an eviction. The permanent
guarantee is the unique index on (showtime_id, seat) in MongoDB, applied when
payment is confirmed.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


# Claim every seat, or none.
#
# Returns an empty array on success, otherwise the seats that are held by
# someone else. Re-locking a seat the caller already holds is allowed and
# refreshes its TTL, which makes the endpoint idempotent under a client retry.
_ACQUIRE_LUA = """
local holder = ARGV[1]
local ttl_ms = tonumber(ARGV[2])
local conflicts = {}

for i = 1, #KEYS do
    local current = redis.call('GET', KEYS[i])
    if current and current ~= holder then
        conflicts[#conflicts + 1] = ARGV[i + 2]
    end
end

if #conflicts > 0 then
    return conflicts
end

for i = 1, #KEYS do
    redis.call('SET', KEYS[i], holder, 'PX', ttl_ms)
end

return {}
"""

# Release only the seats this caller actually holds.
_RELEASE_LUA = """
local holder = ARGV[1]
local released = {}

for i = 1, #KEYS do
    if redis.call('GET', KEYS[i]) == holder then
        redis.call('DEL', KEYS[i])
        released[#released + 1] = ARGV[i + 1]
    end
end

return released
"""

# Extend only the seats this caller still holds. A seat whose TTL already
# lapsed is not resurrected: it is gone, and the caller is told so.
_EXTEND_LUA = """
local holder = ARGV[1]
local ttl_ms = tonumber(ARGV[2])
local extended = {}

for i = 1, #KEYS do
    if redis.call('GET', KEYS[i]) == holder then
        redis.call('PEXPIRE', KEYS[i], ttl_ms)
        extended[#extended + 1] = ARGV[i + 2]
    end
end

return extended
"""


class LockServices:
    """Acquire, release, extend and inspect seat locks."""

    def __init__(self, redis: Redis):
        self.redis = redis
        self._acquire = redis.register_script(_ACQUIRE_LUA)
        self._release = redis.register_script(_RELEASE_LUA)
        self._extend = redis.register_script(_EXTEND_LUA)

    @staticmethod
    def key(showtime_id: str, seat: str) -> str:
        return f"lock:{showtime_id}:{seat}"

    def _keys(self, showtime_id: str, seats: List[str]) -> List[str]:
        return [self.key(showtime_id, seat) for seat in seats]

    async def acquire(self, showtime_id: str, seats: List[str], holder: str,
                      ttl_seconds: int) -> Tuple[bool, List[str]]:
        """Claim every seat or none.

        Returns (True, []) on success, or (False, conflicting_seats).
        """
        conflicts = await self._acquire(
            keys=self._keys(showtime_id, seats),
            args=[holder, int(ttl_seconds * 1000), *seats],
        )

        if conflicts:
            taken = [c.decode() if isinstance(c, bytes) else c
                     for c in conflicts]
            logger.info("Lock refused for %s on %s: %s held by others",
                        holder, showtime_id, taken)
            return False, taken

        logger.info("Locked %s on %s for %s (%ss)",
                    seats, showtime_id, holder, ttl_seconds)
        return True, []

    async def release(self, showtime_id: str, seats: List[str],
                      holder: str) -> List[str]:
        """Free the seats this caller holds, ignoring any it does not."""
        released = await self._release(
            keys=self._keys(showtime_id, seats),
            args=[holder, *seats],
        )
        freed = [s.decode() if isinstance(s, bytes) else s for s in released]

        if freed:
            logger.info("Released %s on %s for %s", freed, showtime_id, holder)
        return freed

    async def extend(self, showtime_id: str, seats: List[str], holder: str,
                     ttl_seconds: int) -> List[str]:
        """Push the expiry out on the seats this caller still holds."""
        extended = await self._extend(
            keys=self._keys(showtime_id, seats),
            args=[holder, int(ttl_seconds * 1000), *seats],
        )
        return [s.decode() if isinstance(s, bytes) else s for s in extended]

    async def holders(self, showtime_id: str,
                      seats: List[str]) -> dict[str, str]:
        """Map each currently locked seat to its holder.

        A single MGET rather than a key scan: the seats of a hall are known, so
        the read is one round trip with a predictable cost, and SCAN over a
        shared keyspace would be neither.
        """
        if not seats:
            return {}

        values = await self.redis.mget(self._keys(showtime_id, seats))
        return {
            seat: (value.decode() if isinstance(value, bytes) else value)
            for seat, value in zip(seats, values)
            if value
        }

    @staticmethod
    def expires_at(ttl_seconds: int) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
