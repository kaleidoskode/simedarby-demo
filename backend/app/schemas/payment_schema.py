"""Payment and ticket models.

Card details are accepted, validated and immediately discarded. Only the last
four digits are kept, on the booking, so a user can recognise which card they
used. Nothing else about the card is stored anywhere: a real deployment would
send it straight to a payment provider and never let it reach this service at
all, and modelling it that way here keeps the shape honest.
"""

import re
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_schema import Money, PaymentMethod, PaymentStatus

_DIGITS = re.compile(r"\D")
_EXPIRY = re.compile(r"^(0[1-9]|1[0-2])\s*/\s*(\d{2})$")


def _luhn_ok(number: str) -> bool:
    """Validate a card number's check digit.

    Catches a mistyped digit before anything is attempted, which is what the
    check digit exists for.
    """
    total = 0
    for index, digit in enumerate(reversed(number)):
        value = int(digit)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


class CardDetails(BaseModel):
    """The Card payment screen."""

    number: str = Field(..., examples=["4242 4242 4242 4242"],
                        description="Digits, spaces are ignored")
    expiry: str = Field(..., examples=["12/29"], description="MM/YY")
    cvv: str = Field(..., examples=["123"], min_length=3, max_length=4)

    @field_validator("number")
    @classmethod
    def check_number(cls, number: str) -> str:
        digits = _DIGITS.sub("", number)
        if not 13 <= len(digits) <= 19:
            raise ValueError("Card number must be between 13 and 19 digits")
        if not _luhn_ok(digits):
            raise ValueError("Card number is not valid")
        return digits

    @field_validator("expiry")
    @classmethod
    def check_expiry(cls, expiry: str) -> str:
        match = _EXPIRY.match(expiry.strip())
        if not match:
            raise ValueError("Expiry must be in MM/YY format")

        month, year = int(match.group(1)), 2000 + int(match.group(2))
        now = datetime.now(timezone.utc)
        # A card is valid through the end of its expiry month.
        if (year, month) < (now.year, now.month):
            raise ValueError("Card has expired")
        return f"{month:02d}/{str(year)[2:]}"

    @field_validator("cvv")
    @classmethod
    def check_cvv(cls, cvv: str) -> str:
        if not cvv.isdigit():
            raise ValueError("CVV must be digits")
        return cvv


class PaymentRequest(BaseModel):
    """Body of the pay endpoint."""

    method: PaymentMethod = Field(..., examples=["debit_card"])
    card: Optional[CardDetails] = Field(
        default=None, description="Required when method is debit_card")
    save_card: bool = Field(
        default=False,
        description="Accepted so the design's checkbox has somewhere to go. "
                    "Nothing is stored either way; honouring it would need a "
                    "provider vault and a real account to attach it to.")


class PaymentMethodOption(BaseModel):
    """One row on the Payment screen."""

    id: PaymentMethod
    label: str = Field(..., examples=["Debit card"])
    description: str = Field(..., examples=["Pay with Visa or Mastercard"])
    requires_card: bool = Field(
        ..., description="Whether the card form is shown next")


class PaymentReceipt(BaseModel):
    """The outcome of a payment attempt."""

    booking_id: str
    reference: str = Field(..., examples=["CBK-8QP4R2"])
    status: PaymentStatus
    method: PaymentMethod
    amount: Money
    transaction_reference: Optional[str] = Field(
        default=None, examples=["PAY-7F3A9C21"])
    card_last4: Optional[str] = Field(default=None, examples=["4242"])
    paid_at: Optional[datetime] = None


class Ticket(BaseModel):
    """The View ticket screen, after a successful booking."""

    reference: str = Field(..., examples=["CBK-8QP4R2"])
    movie_title: str = Field(..., examples=["Venom: Let There Be Carnage"])
    poster_url: Optional[str] = None
    cinema_name: str = Field(..., examples=["GSC Mid Valley Megamall"])
    hall_name: str = Field(..., examples=["Hall 1"])
    seats: List[str] = Field(..., examples=[["F4", "F5"]])
    ticket_class: str = Field(..., examples=["Classic"])
    display_date: str = Field(..., examples=["Aug 14, 2026"])
    start_display: str = Field(..., examples=["5:40PM"])
    end_display: str = Field(..., examples=["7:20PM"])
    starts_at: datetime
    total_paid: Money
    issued_at: datetime
    qr_payload: str = Field(
        ...,
        description="Encoded into the QR code scanned at the door. The booking "
                    "reference alone, so a scan is a lookup rather than a "
                    "credential that could be forged from its contents.",
        examples=["CBK-8QP4R2"])
