"""Booking, reservation and payment models."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common_schema import (
    BookingStatus,
    Money,
    PaymentMethod,
    PaymentStatus,
)


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


class Booking(BaseModel):
    """A booking from seat selection through to confirmation."""

    id: str = Field(..., examples=["bkg_9f2a7c1e"])
    reference: str = Field(..., examples=["CBK-8QP4R2"])
    user_id: str = Field(..., examples=["usr_8f2a"])
    showtime_id: str
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


