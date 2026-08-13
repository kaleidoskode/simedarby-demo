"""The seating plan and the operations on it.

Three sources are combined into one view:

    hall layout      MongoDB   which seats physically exist
    reservations     MongoDB   which are sold, permanently
    locks            Redis     which are being chosen right now, briefly

Sold beats locked beats free. The first two are durable, the third is not, and
keeping them in separate stores is deliberate: a lost lock costs a user a
retry, whereas a lost reservation would sell the same seat twice.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.databases.mongodb import collections
from app.middleware.exception import CustomErrorException
from app.schemas.common_schema import Money, SeatStatus
from app.schemas.seat_schema import (
    LockResult,
    ReleaseResult,
    SeatChange,
    SeatChangeList,
    SeatPlan,
    SeatPlanRow,
    SeatPlanSummary,
    SeatState,
)
from app.services.event_services import EventServices
from app.services.lock_services import LockServices

logger = logging.getLogger(__name__)


class SeatServices:
    """Reads the seating plan and mediates the locks on it."""

    def __init__(self, mongo_db1: AsyncIOMotorDatabase, locks: LockServices,
                 events: EventServices):
        self.db = mongo_db1
        self.locks = locks
        self.events = events

    # ---------------------------------------------------------------- loading

    async def _showtime(self, showtime_id: str) -> Dict[str, Any]:
        doc = await self.db[collections.SHOWTIMES].find_one(
            {"_id": showtime_id})
        if not doc:
            raise CustomErrorException(
                f"Showtime '{showtime_id}' not found", status_code=404)
        return doc

    async def _hall(self, hall_id: str) -> Dict[str, Any]:
        doc = await self.db[collections.HALLS].find_one({"_id": hall_id})
        if not doc:
            # The showtime references it, so a miss is broken data rather than
            # a bad request.
            raise CustomErrorException(
                f"Hall '{hall_id}' referenced by the showtime is missing",
                status_code=500)
        return doc

    @staticmethod
    def _layout(hall: Dict[str, Any]) -> List[tuple]:
        """Flatten the hall into ordered (row, number, seat) triples."""
        return [
            (row["row"], number, f"{row['row']}{number}")
            for row in hall["rows"]
            for number in row["seat_numbers"]
        ]

    async def _booked(self, showtime_id: str) -> Set[str]:
        cursor = self.db[collections.SEAT_RESERVATIONS].find(
            {"showtime_id": showtime_id}, {"seat": 1})
        return {doc["seat"] async for doc in cursor}

    # ------------------------------------------------------------------- plan

    async def get_plan(self, showtime_id: str, viewer_id: str = "") -> SeatPlan:
        """Build the Select Seat screen for one caller.

        `viewer_id` decides only how a locked seat is labelled, never whether
        it is locked: the caller's own holds come back as `held_by_me` so the
        client can render them as Selected rather than unavailable.
        """
        showtime = await self._showtime(showtime_id)
        hall = await self._hall(showtime["hall_id"])

        layout = self._layout(hall)
        all_seats = [seat for _, _, seat in layout]

        booked = await self._booked(showtime_id)
        held = await self.locks.holders(showtime_id, all_seats)

        # Read the stream position after the state above, never before. A
        # change landing mid-read is then included in the plan and also sits at
        # or below this version, so a client polling from here re-applies it
        # harmlessly. The reverse order could hide a change entirely.
        version = await self.events.latest_version(showtime_id)

        rows: List[SeatPlanRow] = []
        counts = {SeatStatus.available: 0, SeatStatus.locked: 0,
                  SeatStatus.booked: 0}

        for row_def in hall["rows"]:
            states: List[SeatState] = []
            for number in row_def["seat_numbers"]:
                seat = f"{row_def['row']}{number}"

                if seat in booked:
                    status = SeatStatus.booked
                    mine = False
                elif seat in held:
                    status = SeatStatus.locked
                    mine = bool(viewer_id) and held[seat] == viewer_id
                else:
                    status = SeatStatus.available
                    mine = False

                counts[status] += 1
                states.append(SeatState(seat=seat, row=row_def["row"],
                                        number=number, status=status,
                                        held_by_me=mine))
            rows.append(SeatPlanRow(row=row_def["row"], seats=states))

        return SeatPlan(
            showtime_id=showtime_id,
            hall_id=hall["_id"],
            hall_name=hall["name"],
            price=Money.of(showtime["price_minor"],
                           showtime.get("currency", settings.currency)),
            rows=rows,
            summary=SeatPlanSummary(
                total=len(all_seats),
                available=counts[SeatStatus.available],
                locked=counts[SeatStatus.locked],
                booked=counts[SeatStatus.booked],
            ),
            version=version,
        )

    async def get_changes(self, showtime_id: str, since: str,
                          viewer_id: str = "") -> SeatChangeList:
        """Everything that happened after `since`.

        The polling counterpart to the WebSocket, reading the same log, so the
        two transports cannot disagree about what happened. Useful as a
        fallback on a network where a socket will not stay up.
        """
        await self._showtime(showtime_id)

        try:
            entries = await self.events.read_since(showtime_id, since)
        except ValueError as exc:
            raise CustomErrorException(str(exc), status_code=422) from exc

        changes = [
            SeatChange(
                seat=entry["seat"],
                status=entry["status"],
                # Resolved per caller, so a holder's id is never handed to
                # anyone else.
                held_by_me=bool(viewer_id) and entry.get("holder") == viewer_id,
                at=entry["at"],
            )
            for entry in entries
        ]

        # When nothing changed, echo the caller's position rather than the
        # stream head: the client is already up to date and should keep polling
        # from where it is.
        version = entries[-1]["id"] if entries else since

        return SeatChangeList(showtime_id=showtime_id, version=version,
                              changes=changes)

    # ------------------------------------------------------------ validation

    async def _validate(self, showtime_id: str, seats: List[str],
                        holder: str) -> Dict[str, Any]:
        """Reject anything the lock script cannot judge for itself."""
        showtime = await self._showtime(showtime_id)

        if showtime["starts_at"] <= datetime.now(timezone.utc):
            raise CustomErrorException(
                "This screening has already started", status_code=409)

        hall = await self._hall(showtime["hall_id"])
        all_seats = [seat for _, _, seat in self._layout(hall)]
        existing = set(all_seats)

        unknown = [seat for seat in seats if seat not in existing]
        if unknown:
            raise CustomErrorException(
                f"No such seat in {hall['name']}: {', '.join(unknown)}",
                status_code=422,
                details={"unknown_seats": unknown})

        # The limit is on what the caller ends up holding, not on one request.
        # Counting per request would let a user take ten seats, then ten more,
        # and book all twenty.
        held = await self.locks.holders(showtime_id, all_seats)
        already_mine = {seat for seat, owner in held.items()
                        if owner == holder}
        total_after = len(already_mine | set(seats))

        if total_after > settings.max_seats_per_booking:
            raise CustomErrorException(
                f"A booking is limited to {settings.max_seats_per_booking} "
                f"seats. You already hold {len(already_mine)} and asked for "
                f"{len(seats)} more.",
                status_code=422,
                details={"limit": settings.max_seats_per_booking,
                         "already_held": sorted(already_mine),
                         "requested": seats})

        return showtime

    # ------------------------------------------------------------------ locks

    async def lock(self, showtime_id: str, seats: List[str],
                   holder: str) -> LockResult:
        """Hold seats for this caller, all of them or none."""
        await self._validate(showtime_id, seats, holder)

        # A sold seat is checked here because the Redis script cannot see
        # MongoDB. This is a courtesy so the user is told immediately; the
        # binding check is the unique index at payment.
        booked = await self._booked(showtime_id)
        already_sold = [seat for seat in seats if seat in booked]
        if already_sold:
            raise CustomErrorException(
                f"Already booked: {', '.join(already_sold)}",
                status_code=409,
                details={"conflicts": already_sold, "reason": "booked"})

        ttl = settings.seat_lock_ttl_seconds
        acquired, conflicts = await self.locks.acquire(
            showtime_id, seats, holder, ttl)

        if not acquired:
            raise CustomErrorException(
                f"Someone is already holding: {', '.join(conflicts)}",
                status_code=409,
                details={"conflicts": conflicts, "reason": "locked"})

        await self.events.publish(showtime_id, [
            {"seat": seat, "status": SeatStatus.locked.value, "holder": holder}
            for seat in seats
        ])

        return LockResult(
            showtime_id=showtime_id, seats=seats, holder=holder,
            ttl_seconds=ttl, expires_at=self.locks.expires_at(ttl))

    async def release(self, showtime_id: str, seats: List[str],
                      holder: str) -> ReleaseResult:
        """Give up seats this caller holds."""
        await self._showtime(showtime_id)

        released = await self.locks.release(showtime_id, seats, holder)
        ignored = [seat for seat in seats if seat not in released]

        await self.events.publish(showtime_id, [
            {"seat": seat, "status": SeatStatus.available.value, "holder": ""}
            for seat in released
        ])

        return ReleaseResult(showtime_id=showtime_id, released=released,
                             ignored=ignored)

    async def heartbeat(self, showtime_id: str, seats: List[str],
                        holder: str) -> LockResult:
        """Refresh the hold while the user is still choosing.

        A seat whose TTL already lapsed is not revived; it may belong to
        someone else by now. The caller is told which seats it still has, and
        an empty result means the selection is gone.
        """
        await self._showtime(showtime_id)

        ttl = settings.seat_lock_ttl_seconds
        extended = await self.locks.extend(showtime_id, seats, holder, ttl)

        lost = [seat for seat in seats if seat not in extended]
        if lost:
            logger.info("Hold lapsed for %s on %s: %s", holder, showtime_id,
                        lost)

        return LockResult(
            showtime_id=showtime_id, seats=extended, holder=holder,
            ttl_seconds=ttl, expires_at=self.locks.expires_at(ttl))
