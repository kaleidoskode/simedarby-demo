"""Shared enums and value objects for the cinema booking domain."""

from enum import Enum
from typing import Generic, List, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def normalise_seats(seats: List[str]) -> List[str]:
    """Upper-case, trim and de-duplicate seat labels, preserving order.

    Shared by every request body that carries a seat list, so the seat "f4 "
    means the same thing wherever it is sent.

    De-duplication matters beyond tidiness: ["F4", "F4"] would otherwise pass
    the same key to the lock script twice and count as two seats against the
    per-booking limit.
    """
    seen: List[str] = []
    for seat in seats:
        cleaned = seat.strip().upper()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    if not seen:
        raise ValueError("At least one seat is required")
    return seen


class MovieSection(str, Enum):
    """Groupings shown on the home screen."""

    new_release = "new_release"
    popular = "popular"
    recommended = "recommended"


class SeatStatus(str, Enum):
    """State of a single seat on the seating plan.

    `available` and `booked` come from MongoDB. `locked` is held in Redis with
    a TTL and is what makes the plan update in real time; the client renders it
    as `selected` when the holder is the current user, and as unavailable
    otherwise.
    """

    available = "available"
    locked = "locked"
    booked = "booked"


class BookingStatus(str, Enum):
    """Lifecycle of a booking.

    draft            seats held, user still choosing food or reviewing
    awaiting_payment checkout entered, locks extended to the payment window
    confirmed        paid, seats written to seat_reservations permanently
    cancelled        abandoned by the user, locks released
    expired          the hold lapsed before payment completed
    """

    draft = "draft"
    awaiting_payment = "awaiting_payment"
    confirmed = "confirmed"
    cancelled = "cancelled"
    expired = "expired"


# A booking still in play: its food order can change and it can be paid for.
# Held as plain strings because that is how the status is stored in MongoDB, so
# every comparison is like for like.
OPEN_BOOKING_STATUSES = frozenset({
    BookingStatus.draft.value,
    BookingStatus.awaiting_payment.value,
})


class PaymentMethod(str, Enum):
    debit_card = "debit_card"
    bank_transfer = "bank_transfer"
    crypto_wallet = "crypto_wallet"


class PaymentStatus(str, Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"


class FnbCategory(str, Enum):
    combo = "combo"
    food_snacks = "food_snacks"
    beverages = "beverages"


# Currencies whose smallest unit is the unit itself, so they take no decimals.
_ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "VND", "IDR"}

_CURRENCY_SYMBOLS = {"MYR": "RM", "SGD": "S$", "USD": "$", "GBP": "£",
                     "EUR": "€", "NGN": "₦", "JPY": "¥"}


class Money(BaseModel):
    """An amount in minor units, with a preformatted display string.

    Amounts are integers in the currency's minor unit (sen for MYR). Floats are
    never used for money: repeated addition of values such as 0.1 does not
    round-trip exactly, and a booking total is summed from several lines.
    """

    minor: int = Field(..., description="Amount in minor units, e.g. sen",
                       examples=[2500])
    currency: str = Field(default="MYR", examples=["MYR"])
    display: str = Field(..., description="Preformatted for the UI",
                         examples=["RM25.00"])

    @classmethod
    def of(cls, minor: int, currency: str = "MYR") -> "Money":
        """Build a Money value, formatting the display string."""
        symbol = _CURRENCY_SYMBOLS.get(currency, f"{currency} ")
        sign = "-" if minor < 0 else ""

        if currency in _ZERO_DECIMAL_CURRENCIES:
            return cls(minor=minor, currency=currency,
                       display=f"{sign}{symbol}{abs(minor):,}")

        major, remainder = divmod(abs(minor), 100)
        return cls(minor=minor, currency=currency,
                   display=f"{sign}{symbol}{major:,}.{remainder:02d}")


class PageMeta(BaseModel):
    """Pagination envelope metadata."""

    page: int = Field(..., ge=1, examples=[1])
    limit: int = Field(..., ge=1, examples=[20])
    total: int = Field(..., ge=0, examples=[4])
    total_pages: int = Field(..., ge=0, examples=[1])


class Page(BaseModel, Generic[T]):
    """A page of results plus its metadata."""

    items: List[T]
    meta: PageMeta
