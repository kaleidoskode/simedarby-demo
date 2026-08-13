"""Payment, seat reservation and ticket issue.

This is where a hold becomes a sale, and where the guarantee behind "first come
first serve" is finally enforced by the database rather than by a lock.

The order of operations is deliberate:

    1. claim the booking   atomic, so two simultaneous requests cannot both pay
    2. reserve the seats   the unique index binds here; cheap and reversible
    3. charge              the irreversible step, done last
    4. confirm

Reserving before charging means a seat clash costs the user nothing: no money
has moved yet. Charging first and then failing to reserve would mean taking
payment for seats that were never allocated, which needs a refund to undo.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError

from app.core.config import settings
from app.databases.mongodb import collections
from app.middleware.exception import CustomErrorException
from app.schemas.auth_schema import CurrentUser
from app.schemas.booking_schema import Booking
from app.schemas.common_schema import (
    OPEN_BOOKING_STATUSES,
    BookingStatus,
    Money,
    PaymentMethod,
    PaymentStatus,
    SeatStatus,
)
from app.schemas.payment_schema import (
    PaymentMethodOption,
    PaymentRequest,
    Ticket,
)
from app.services.booking_services import BookingServices
from app.services.event_services import EventServices
from app.services.lock_services import LockServices

logger = logging.getLogger(__name__)


# The three options on the Payment screen.
PAYMENT_METHODS = [
    PaymentMethodOption(
        id=PaymentMethod.debit_card,
        label="Debit card",
        description="Pay with Visa or Mastercard",
        requires_card=True),
    PaymentMethodOption(
        id=PaymentMethod.bank_transfer,
        label="Bank Transfer",
        description="Make a transfer from your bank account",
        requires_card=False),
    PaymentMethodOption(
        id=PaymentMethod.crypto_wallet,
        label="Crypto wallets",
        description="Pay from your cryptocurrency wallet",
        requires_card=False),
]

# Cards ending in these digits are declined by the simulated gateway, so the
# failure path can be demonstrated without a real provider. The convention
# matches the test numbers most providers publish.
_DECLINE_SUFFIXES = ("0002", "0000")


class PaymentServices:
    """Takes payment, reserves seats permanently and issues the ticket."""

    def __init__(self, mongo_db1: AsyncIOMotorDatabase, locks: LockServices,
                 events: EventServices, bookings: BookingServices):
        self.db = mongo_db1
        self.locks = locks
        self.events = events
        self.bookings = bookings

    # ---------------------------------------------------------------- methods

    @staticmethod
    def list_methods() -> List[PaymentMethodOption]:
        """The Payment screen's options."""
        return PAYMENT_METHODS

    # ------------------------------------------------------------------- pay

    async def pay(self, user: CurrentUser, booking_id: str,
                  payload: PaymentRequest,
                  idempotency_key: Optional[str]) -> Booking:
        """Charge for a booking and reserve its seats permanently."""
        doc = await self.bookings.load_for_user(booking_id, user)

        replay = self._replay_if_same_request(doc, idempotency_key)
        if replay is not None:
            return replay

        if doc["status"] not in OPEN_BOOKING_STATUSES:
            raise CustomErrorException(
                f"This booking is {doc['status']} and cannot be paid for",
                status_code=409)

        if payload.method is PaymentMethod.debit_card and not payload.card:
            raise CustomErrorException(
                "Card details are required for a debit card payment",
                status_code=422)

        await self._require_seats_still_held(doc, user)

        claimed = await self._claim(doc, idempotency_key)
        seats, showtime_id = claimed["seats"], claimed["showtime_id"]

        # 2. Reserve. The unique index on (showtime_id, seat) is what makes a
        #    seat impossible to sell twice, whatever the lock believed.
        await self._reserve(showtime_id, seats, booking_id, user.id)

        # 3. Charge. Last, because it is the step that cannot be undone
        #    without a refund.
        try:
            outcome = self._charge(claimed, payload)
        except CustomErrorException:
            await self._release_reservations(booking_id)
            await self._revert_claim(booking_id)
            raise

        # 4. Confirm.
        now = datetime.now(timezone.utc)
        payment = {
            "method": payload.method.value,
            "status": PaymentStatus.succeeded.value,
            "reference": outcome["reference"],
            "card_last4": outcome["card_last4"],
            "paid_at": now,
            "idempotency_key": idempotency_key,
        }

        confirmed = await self.db[collections.BOOKINGS].find_one_and_update(
            {"_id": booking_id},
            {"$set": {"status": BookingStatus.confirmed.value,
                      "payment": payment,
                      "confirmed_at": now,
                      "expires_at": None}},
            return_document=ReturnDocument.AFTER)

        # The hold has done its job; the reservation is now authoritative.
        # Dropping the keys frees Redis immediately rather than waiting out a
        # TTL on seats that can no longer be taken by anyone.
        await self.locks.release(showtime_id, seats, user.id)
        await self.events.publish(showtime_id, [
            {"seat": seat, "status": SeatStatus.booked.value, "holder": ""}
            for seat in seats
        ])

        logger.info("Booking %s confirmed for %s: %s paid %s",
                    booking_id, user.id, seats, outcome["reference"])

        return self.bookings.to_model(confirmed)

    # --------------------------------------------------------------- internals

    def _replay_if_same_request(self, doc: Dict[str, Any],
                                idempotency_key: Optional[str]
                                ) -> Optional[Booking]:
        """Return the original result when this request was already handled.

        A retry on a flaky mobile network must not charge twice. With the same
        Idempotency-Key the caller gets the original outcome; with a different
        one, an already paid booking is a conflict rather than a second sale.
        """
        if doc["status"] != BookingStatus.confirmed.value:
            return None

        stored = (doc.get("payment") or {}).get("idempotency_key")
        if idempotency_key and stored and stored == idempotency_key:
            logger.info("Idempotent replay of payment for %s", doc["_id"])
            return self.bookings.to_model(doc)

        raise CustomErrorException(
            "This booking has already been paid for", status_code=409,
            details={"reference": doc["reference"],
                     "status": doc["status"]})

    async def _require_seats_still_held(self, doc: Dict[str, Any],
                                        user: CurrentUser) -> None:
        """Refuse if the hold lapsed while the user was on the payment screen."""
        held = await self.locks.holders(doc["showtime_id"], doc["seats"])
        lost = [seat for seat in doc["seats"] if held.get(seat) != user.id]

        if lost:
            raise CustomErrorException(
                f"Your hold on {', '.join(lost)} has expired. "
                "Please select seats again.",
                status_code=409,
                details={"conflicts": lost, "reason": "hold_expired"})

    async def _claim(self, doc: Dict[str, Any],
                     idempotency_key: Optional[str]) -> Dict[str, Any]:
        """Move the booking to awaiting_payment, atomically.

        Two identical requests arriving together would otherwise both pass the
        status check and both charge. Only one update can match a payable
        status, so only one proceeds.
        """
        claimed = await self.db[collections.BOOKINGS].find_one_and_update(
            {"_id": doc["_id"], "status": {"$in": list(OPEN_BOOKING_STATUSES)}},
            {"$set": {"status": BookingStatus.awaiting_payment.value,
                      "payment.idempotency_key": idempotency_key}},
            return_document=ReturnDocument.AFTER)

        if not claimed:
            raise CustomErrorException(
                "This booking is already being paid for", status_code=409)
        return claimed

    async def _revert_claim(self, booking_id: str) -> None:
        """Put a booking back to draft after a declined charge, so it can be
        retried with another card."""
        await self.db[collections.BOOKINGS].update_one(
            {"_id": booking_id,
             "status": BookingStatus.awaiting_payment.value},
            {"$set": {"status": BookingStatus.draft.value,
                      "payment.status": PaymentStatus.failed.value}})

    async def _reserve(self, showtime_id: str, seats: List[str],
                       booking_id: str, user_id: str) -> None:
        """Write the permanent reservations, or fail with the clashing seats."""
        now = datetime.now(timezone.utc)
        documents = [
            {
                "_id": f"res_{showtime_id}_{seat}",
                "showtime_id": showtime_id,
                "seat": seat,
                "booking_id": booking_id,
                "user_id": user_id,
                "created_at": now,
            }
            for seat in seats
        ]

        try:
            await self.db[collections.SEAT_RESERVATIONS].insert_many(
                documents, ordered=False)
        except BulkWriteError as exc:
            taken = self._clashing_seats(exc)

            # ordered=False means the seats that did not clash were written. A
            # booking must be all of its seats or none, so those are undone.
            #
            # Only the rows this attempt actually inserted are removed, chosen
            # by id rather than by booking_id. Deleting by booking_id would be
            # wrong if another request for the same booking were reserving
            # concurrently: this rollback would take away rows that request had
            # just written and still believes it owns.
            failed = self._failed_ids(exc)
            inserted = [doc["_id"] for doc in documents
                        if doc["_id"] not in failed]
            if inserted:
                await self.db[collections.SEAT_RESERVATIONS].delete_many(
                    {"_id": {"$in": inserted}})

            logger.warning("Reservation clash on %s for %s: %s",
                           showtime_id, booking_id, taken)
            raise CustomErrorException(
                f"These seats were taken while you were paying: "
                f"{', '.join(taken)}",
                status_code=409,
                details={"conflicts": taken, "reason": "booked"}) from exc

    @staticmethod
    def _failed_ids(exc: BulkWriteError) -> set:
        """Ids the driver reported as rejected, so the rest were inserted."""
        ids = set()
        for error in exc.details.get("writeErrors", []):
            document = error.get("op") or {}
            if document.get("_id"):
                ids.add(document["_id"])
        return ids

    @staticmethod
    def _clashing_seats(exc: BulkWriteError) -> List[str]:
        """Pull the seat labels out of a duplicate key error."""
        seats = []
        for error in exc.details.get("writeErrors", []):
            seat = (error.get("keyValue") or {}).get("seat")
            if seat:
                seats.append(seat)
            else:
                # Fall back to the generated id when the driver does not report
                # the offending key.
                document = error.get("op") or {}
                if document.get("seat"):
                    seats.append(document["seat"])
        return sorted(set(seats))

    async def _release_reservations(self, booking_id: str) -> None:
        await self.db[collections.SEAT_RESERVATIONS].delete_many(
            {"booking_id": booking_id})

    def _charge(self, doc: Dict[str, Any],
                payload: PaymentRequest) -> Dict[str, Any]:
        """Simulated payment provider.

        A real integration would call a provider here and handle its webhook.
        The behaviour that matters for the rest of the flow is the same: it
        either succeeds with a reference, or it declines and nothing is taken.
        """
        card_last4 = None

        if payload.method is PaymentMethod.debit_card:
            number = payload.card.number
            card_last4 = number[-4:]

            if number.endswith(_DECLINE_SUFFIXES):
                logger.info("Simulated decline for booking %s", doc["_id"])
                raise CustomErrorException(
                    "Your card was declined. Try another payment method.",
                    status_code=402,
                    details={"reason": "card_declined",
                             "card_last4": card_last4})

        return {
            "reference": f"PAY-{uuid.uuid4().hex[:8].upper()}",
            "card_last4": card_last4,
        }

    # ---------------------------------------------------------------- ticket

    async def get_ticket(self, user: CurrentUser, booking_id: str) -> Ticket:
        """The View ticket screen, available once a booking is confirmed."""
        doc = await self.bookings.load_for_user(booking_id, user)

        if doc["status"] != BookingStatus.confirmed.value:
            raise CustomErrorException(
                f"No ticket yet: this booking is {doc['status']}",
                status_code=409,
                details={"status": doc["status"]})

        screening = doc["screening"]
        currency = doc.get("currency", settings.currency)

        return Ticket(
            reference=doc["reference"],
            movie_title=screening["movie_title"],
            poster_url=screening.get("poster_url"),
            cinema_name=screening["cinema_name"],
            hall_name=screening["hall_name"],
            seats=doc["seats"],
            ticket_class=doc.get("ticket_class", "Classic"),
            display_date=screening["display_date"],
            start_display=screening["start_display"],
            end_display=screening["end_display"],
            starts_at=screening["starts_at"],
            total_paid=Money.of(doc["amounts"]["total_minor"], currency),
            issued_at=doc.get("confirmed_at") or doc["created_at"],
            qr_payload=doc["reference"],
        )
