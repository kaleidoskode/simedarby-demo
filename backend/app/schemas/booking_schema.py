"""Booking, reservation and payment models."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_schema import (
    BookingStatus,
    Money,
    PaymentMethod,
    PaymentStatus,
    normalise_seats,
)


class BookingCreate(BaseModel):
    """Body for starting a booking from the seating plan."""

    showtime_id: str = Field(..., examples=["sho_20260814_1740_gsc_mv_1"])
    seats: List[str] = Field(..., min_length=1, examples=[["F4", "F5"]])

    _normalise = field_validator("seats")(normalise_seats)


class FnbSelectionItem(BaseModel):
    """One line of the food and drink order."""

    fnb_id: str = Field(..., examples=["fnb_fresh_xl_combo"])
    quantity: int = Field(..., ge=0, le=99, examples=[1],
                          description="Zero removes the item")


class FnbSelection(BaseModel):
    """Body for setting the food and beverage order.

    The whole order is replaced rather than added to, matching a screen where
    the user adjusts quantities with plus and minus and then confirms. That
    also makes the call idempotent: sending it twice cannot double the order.
    """

    items: List[FnbSelectionItem] = Field(default_factory=list)


class FnbLine(BaseModel):
    """One food or beverage line on a booking."""

    fnb_id: str = Field(..., examples=["fnb_fresh_xl_combo"])
    name: str = Field(..., examples=["Fresh XL Combo"])
    unit_price: Money
    quantity: int = Field(..., ge=1, examples=[1])
    line_total: Money


class BookingAmounts(BaseModel):
    """The money breakdown shown on the Booking Summary screen.

    These are the four lines in the design. Any discount on a food or drink
    item is already reflected in that item's price, so there is no separate
    booking level discount line.
    """

    tickets: Money
    fnb: Money
    service_charge: Money
    total: Money


class PaymentDetail(BaseModel):
    """Outcome of the payment attempt.

    Card details are never stored: only the method, the status and a gateway
    reference are kept.
    """

    method: Optional[PaymentMethod] = None
    status: PaymentStatus = PaymentStatus.pending
    reference: Optional[str] = Field(default=None, examples=["PAY-7F3A9C21"])
    card_last4: Optional[str] = Field(default=None, examples=["4242"])
    paid_at: Optional[datetime] = None


class BookingScreening(BaseModel):
    """What the Booking Summary shows about the screening itself.

    Copied onto the booking rather than joined at read time, so the summary and
    the ticket render from one document and still read correctly years later,
    after the catalogue has moved on.
    """

    showtime_id: str
    movie_title: str = Field(..., examples=["Venom: Let There Be Carnage"])
    genres: List[str] = Field(default_factory=list,
                              examples=[["Action", "Adventure", "Sci-fi"]])
    duration_mins: int = Field(..., examples=[97])
    formats: List[str] = Field(default_factory=list,
                               examples=[["English", "IMDb 3D"]])
    poster_url: Optional[str] = None
    cinema_name: str = Field(..., examples=["GSC Mid Valley Megamall"])
    hall_name: str = Field(..., examples=["Hall 1"])
    display_date: str = Field(..., examples=["Aug 14, 2026"])
    starts_at: datetime
    ends_at: datetime
    start_display: str = Field(..., examples=["5:40PM"])
    end_display: str = Field(..., examples=["7:20PM"])


class Booking(BaseModel):
    """A booking from seat selection through to confirmation."""

    id: str = Field(..., examples=["bkg_9f2a7c1e"])
    reference: str = Field(..., examples=["CBK-8QP4R2"])
    user_id: str = Field(..., examples=["usr_8f2a"])
    showtime_id: str
    screening: BookingScreening
    seats: List[str] = Field(..., examples=[["F4", "F5"]])
    status: BookingStatus
    ticket_class: str = Field(default="Classic")
    fnb_items: List[FnbLine] = Field(default_factory=list)
    amounts: BookingAmounts
    payment: PaymentDetail = Field(default_factory=PaymentDetail)
    created_at: datetime
    expires_at: Optional[datetime] = Field(
        default=None,
        description="When the seat hold lapses if payment does not complete")
    confirmed_at: Optional[datetime] = None


class SeatReservation(BaseModel):
    """A permanently booked seat.

    A unique index on (showtime_id, seat) backs this collection. That index,
    not the Redis lock, is what makes double booking impossible: the lock can
    be lost to a Redis restart, the index cannot.
    """

    id: str
    showtime_id: str
    seat: str = Field(..., examples=["F4"])
    booking_id: str
    user_id: str
    created_at: datetime


