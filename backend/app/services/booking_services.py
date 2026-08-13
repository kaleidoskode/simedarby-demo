"""Bookings: the draft between choosing seats and paying for them.

A booking is created only when the caller already holds the seats. That keeps
the two concepts separate and each doing one job:

    lock     ephemeral, in Redis, "I am choosing this"
    booking  durable, in MongoDB, "this is what I intend to buy"

Creating one extends the holds from the short seat-picking TTL to the longer
checkout window, so a user reading the summary and choosing a payment method
does not lose their seats mid-flow. The booking's own `expires_at` is set to
match, so the two never disagree about when the hold ends.
"""

import logging
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.databases.mongodb import collections
from app.middleware.exception import CustomErrorException
from app.schemas.auth_schema import CurrentUser
from app.schemas.booking_schema import (
    Booking,
    BookingAmounts,
    BookingScreening,
    FnbLine,
    FnbSelectionItem,
    PaymentDetail,
)
from app.schemas.common_schema import (
    OPEN_BOOKING_STATUSES,
    BookingStatus,
    Money,
    SeatStatus,
)
from app.services.event_services import EventServices
from app.services.lock_services import LockServices
from app.utilities.local_time import display_time

logger = logging.getLogger(__name__)

_REFERENCE_ALPHABET = string.ascii_uppercase + string.digits
_REFERENCE_ATTEMPTS = 5


def screening_snapshot(showtime: Dict[str, Any],
                       movie: Optional[Dict[str, Any]],
                       hall: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The screening details copied onto a booking.

    Copied rather than joined at read time, so the summary and the ticket render
    from one document and still read correctly long after the catalogue has
    moved on.

    A module level function because the seeder builds the same snapshot for its
    pre-sold booking. Sharing it is what stops a seeded booking and a real one
    drifting into different shapes.
    """
    movie = movie or {}
    return {
        "showtime_id": showtime["_id"],
        "movie_title": movie.get("title", "Unknown"),
        "genres": movie.get("genres", []),
        "duration_mins": movie.get("duration_mins", 0),
        "formats": movie.get("formats", []),
        "poster_url": movie.get("poster_url"),
        "cinema_name": showtime["cinema_name"],
        "hall_name": (hall or {}).get("name", "Unknown"),
        "display_date": showtime.get("display_date", ""),
        "starts_at": showtime["starts_at"],
        "ends_at": showtime["ends_at"],
        "start_display": showtime.get("display_time", ""),
        "end_display": display_time(showtime["ends_at"]),
    }


class BookingServices:
    """Create, read, amend and cancel bookings."""

    def __init__(self, mongo_db1: AsyncIOMotorDatabase, locks: LockServices,
                 events: EventServices):
        self.db = mongo_db1
        self.locks = locks
        self.events = events

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _reference() -> str:
        """A short human readable booking reference, as printed on a ticket."""
        return "CBK-" + "".join(
            secrets.choice(_REFERENCE_ALPHABET) for _ in range(6))

    def _amounts(self, price_minor: int, seat_count: int,
                 fnb_lines: List[Dict[str, Any]]) -> Dict[str, int]:
        """The four lines of the Booking Summary, in minor units."""
        tickets = price_minor * seat_count
        fnb = sum(line["line_total_minor"] for line in fnb_lines)
        service = settings.service_charge_minor
        return {
            "tickets_minor": tickets,
            "fnb_minor": fnb,
            "service_charge_minor": service,
            "total_minor": tickets + fnb + service,
        }

    def to_model(self, doc: Dict[str, Any]) -> Booking:
        """Turn a stored booking into its API representation.

        Public because the payment service confirms a booking and returns it in
        the same shape, so both paths render a booking identically.
        """
        currency = doc.get("currency", settings.currency)
        amounts = doc["amounts"]
        screening = doc["screening"]

        return Booking(
            id=doc["_id"],
            reference=doc["reference"],
            user_id=doc["user_id"],
            showtime_id=doc["showtime_id"],
            screening=BookingScreening(**screening),
            seats=doc["seats"],
            status=doc["status"],
            ticket_class=doc.get("ticket_class", "Classic"),
            fnb_items=[
                FnbLine(
                    fnb_id=line["fnb_id"],
                    name=line["name"],
                    unit_price=Money.of(line["unit_price_minor"], currency),
                    quantity=line["quantity"],
                    line_total=Money.of(line["line_total_minor"], currency),
                )
                for line in doc.get("fnb_items", [])
            ],
            amounts=BookingAmounts(
                tickets=Money.of(amounts["tickets_minor"], currency),
                fnb=Money.of(amounts["fnb_minor"], currency),
                service_charge=Money.of(amounts["service_charge_minor"],
                                        currency),
                total=Money.of(amounts["total_minor"], currency),
            ),
            payment=PaymentDetail(**doc.get("payment", {})),
            created_at=doc["created_at"],
            expires_at=doc.get("expires_at"),
            confirmed_at=doc.get("confirmed_at"),
        )

    async def load_for_user(self, booking_id: str,
                            user: CurrentUser) -> Dict[str, Any]:
        """Fetch a booking belonging to this caller.

        Someone else's booking is reported as missing rather than forbidden, so
        the endpoint does not confirm that a reference exists to a caller who
        has no business knowing.

        Public because payment loads a booking through the same ownership and
        expiry checks; duplicating them there would be a place for the two to
        drift apart.
        """
        doc = await self.db[collections.BOOKINGS].find_one(
            {"_id": booking_id, "user_id": user.id})
        if not doc:
            raise CustomErrorException(
                f"Booking '{booking_id}' not found", status_code=404)

        return await self._expire_if_lapsed(doc)

    async def _expire_if_lapsed(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Mark a draft expired once its hold has lapsed.

        Resolved on read rather than by a scheduled job. The seats are already
        free at this point, because the Redis TTL released them; this only
        brings the booking's own status into line, and doing it lazily keeps
        the service stateless with nothing to run in the background.
        """
        expires_at = doc.get("expires_at")
        if (doc["status"] in OPEN_BOOKING_STATUSES and expires_at
                and expires_at <= datetime.now(timezone.utc)):
            await self.db[collections.BOOKINGS].update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": BookingStatus.expired.value}})
            doc["status"] = BookingStatus.expired.value
            logger.info("Booking %s expired", doc["_id"])
        return doc

    async def _screening(self, showtime_id: str) -> Dict[str, Any]:
        showtime = await self.db[collections.SHOWTIMES].find_one(
            {"_id": showtime_id})
        if not showtime:
            raise CustomErrorException(
                f"Showtime '{showtime_id}' not found", status_code=404)

        movie = await self.db[collections.MOVIES].find_one(
            {"_id": showtime["movie_id"]})
        hall = await self.db[collections.HALLS].find_one(
            {"_id": showtime["hall_id"]})

        return {
            "showtime": showtime,
            "snapshot": screening_snapshot(showtime, movie, hall),
        }

    # ----------------------------------------------------------------- create

    async def create(self, user: CurrentUser, showtime_id: str,
                     seats: List[str]) -> Booking:
        """Turn a held selection into a draft booking."""
        screening = await self._screening(showtime_id)
        showtime = screening["showtime"]

        if showtime["starts_at"] <= datetime.now(timezone.utc):
            raise CustomErrorException(
                "This screening has already started", status_code=409)

        # Checked here as well as at lock time. The lock endpoint caps what a
        # caller may hold, but this is the endpoint that decides what is
        # actually bought, so it enforces the limit itself rather than assuming
        # the seats arrived through that path.
        if len(seats) > settings.max_seats_per_booking:
            raise CustomErrorException(
                f"A booking is limited to {settings.max_seats_per_booking} "
                f"seats, {len(seats)} requested",
                status_code=422,
                details={"limit": settings.max_seats_per_booking,
                         "requested": len(seats)})

        # The caller must already hold every seat. Without this a client could
        # skip the seating plan and book seats it never locked.
        held = await self.locks.holders(showtime_id, seats)
        not_held = [seat for seat in seats
                    if held.get(seat) != user.id]
        if not_held:
            raise CustomErrorException(
                f"You are not holding: {', '.join(not_held)}. "
                "Select the seats again.",
                status_code=409,
                details={"conflicts": not_held, "reason": "not_held"})

        # Extend from the seat-picking TTL to the checkout window, so the user
        # does not lose their seats while reviewing the summary and paying.
        checkout_ttl = settings.checkout_lock_ttl_seconds
        await self.locks.extend(showtime_id, seats, user.id, checkout_ttl)

        now = datetime.now(timezone.utc)
        amounts = self._amounts(showtime["price_minor"], len(seats), [])

        document = {
            "_id": f"bkg_{uuid.uuid4().hex[:12]}",
            "user_id": user.id,
            "showtime_id": showtime_id,
            "screening": screening["snapshot"],
            "seats": seats,
            "status": BookingStatus.draft.value,
            "ticket_class": showtime.get("ticket_class", "Classic"),
            "fnb_items": [],
            "amounts": amounts,
            "currency": showtime.get("currency", settings.currency),
            "payment": {"status": "pending"},
            "created_at": now,
            "expires_at": now + timedelta(seconds=checkout_ttl),
            "confirmed_at": None,
        }

        await self._insert_with_reference(document)
        logger.info("Booking %s created for %s: %s on %s",
                    document["_id"], user.id, seats, showtime_id)

        return self.to_model(document)

    async def _insert_with_reference(self, document: Dict[str, Any]) -> None:
        """Insert, retrying on the astronomically unlikely reference clash.

        The reference has a unique index, so a collision is a failed insert
        rather than two bookings sharing a printed code.
        """
        for attempt in range(_REFERENCE_ATTEMPTS):
            document["reference"] = self._reference()
            try:
                await self.db[collections.BOOKINGS].insert_one(document)
                return
            except DuplicateKeyError:
                logger.warning("Booking reference collision, retry %d",
                               attempt + 1)

        raise CustomErrorException(
            "Could not allocate a booking reference", status_code=500)

    # ------------------------------------------------------------------ reads

    async def get(self, user: CurrentUser, booking_id: str) -> Booking:
        """One booking, as shown on the Booking Summary screen."""
        return self.to_model(await self.load_for_user(booking_id, user))

    async def list_mine(self, user: CurrentUser) -> List[Booking]:
        """Every booking belonging to the caller, newest first."""
        cursor = (self.db[collections.BOOKINGS]
                  .find({"user_id": user.id})
                  .sort("created_at", -1)
                  .limit(50))
        return [self.to_model(await self._expire_if_lapsed(doc))
                async for doc in cursor]

    # -------------------------------------------------------------------- F&B

    async def set_fnb(self, user: CurrentUser, booking_id: str,
                      items: List[FnbSelectionItem]) -> Booking:
        """Replace the food and drink order and recompute the total."""
        doc = await self.load_for_user(booking_id, user)

        if doc["status"] not in OPEN_BOOKING_STATUSES:
            raise CustomErrorException(
                f"This booking is {doc['status']} and can no longer be changed",
                status_code=409)

        wanted = {item.fnb_id: item.quantity
                  for item in items if item.quantity > 0}

        lines: List[Dict[str, Any]] = []
        if wanted:
            cursor = self.db[collections.FNB_ITEMS].find(
                {"_id": {"$in": list(wanted)}})
            found = {item["_id"]: item async for item in cursor}

            missing = sorted(set(wanted) - set(found))
            if missing:
                raise CustomErrorException(
                    f"No such item: {', '.join(missing)}", status_code=422,
                    details={"unknown_items": missing})

            unavailable = sorted(
                item_id for item_id, item in found.items()
                if not item.get("is_available", True))
            if unavailable:
                raise CustomErrorException(
                    f"Currently unavailable: {', '.join(unavailable)}",
                    status_code=409,
                    details={"unavailable_items": unavailable})

            # Priced from the catalogue, never from the request, so a client
            # cannot choose what it pays.
            for item_id, quantity in wanted.items():
                item = found[item_id]
                lines.append({
                    "fnb_id": item_id,
                    "name": item["name"],
                    "unit_price_minor": item["price_minor"],
                    "quantity": quantity,
                    "line_total_minor": item["price_minor"] * quantity,
                })

        showtime = await self.db[collections.SHOWTIMES].find_one(
            {"_id": doc["showtime_id"]}, {"price_minor": 1})
        amounts = self._amounts(showtime["price_minor"], len(doc["seats"]),
                                lines)

        await self.db[collections.BOOKINGS].update_one(
            {"_id": booking_id},
            {"$set": {"fnb_items": lines, "amounts": amounts}})

        doc["fnb_items"] = lines
        doc["amounts"] = amounts
        logger.info("Booking %s food order set to %d line(s)", booking_id,
                    len(lines))

        return self.to_model(doc)

    # ----------------------------------------------------------------- cancel

    async def cancel(self, user: CurrentUser, booking_id: str) -> Booking:
        """Abandon a booking and hand the seats straight back."""
        doc = await self.load_for_user(booking_id, user)

        if doc["status"] == BookingStatus.confirmed.value:
            raise CustomErrorException(
                "A confirmed booking cannot be cancelled here", status_code=409)

        if doc["status"] in {BookingStatus.cancelled.value,
                             BookingStatus.expired.value}:
            return self.to_model(doc)

        released = await self.locks.release(doc["showtime_id"], doc["seats"],
                                            user.id)

        # Tell everyone watching the plan, so the seats reappear as available
        # without waiting for the TTL that would otherwise have freed them.
        await self.events.publish(doc["showtime_id"], [
            {"seat": seat, "status": SeatStatus.available.value, "holder": ""}
            for seat in released
        ])

        await self.db[collections.BOOKINGS].update_one(
            {"_id": booking_id},
            {"$set": {"status": BookingStatus.cancelled.value,
                      "expires_at": None}})
        doc["status"] = BookingStatus.cancelled.value
        doc["expires_at"] = None

        logger.info("Booking %s cancelled, released %s", booking_id, released)
        return self.to_model(doc)
