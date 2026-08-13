"""Payment and ticket endpoints: the last steps of the flowchart."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Header, Path

from app.core.construct_services import payments as payment_service
from app.core.security import get_current_user
from app.helpers.generic_response import GenericResponse
from app.schemas.auth_schema import CurrentUser
from app.schemas.booking_schema import Booking
from app.schemas.payment_schema import (
    PaymentMethodOption,
    PaymentRequest,
    Ticket,
)
from app.services import payment_services

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/payment-methods",
            response_model=GenericResponse[List[PaymentMethodOption]],
            tags=["payment"], summary="List payment methods")
async def list_payment_methods(
    *,
    service: payment_services.PaymentServices = Depends(payment_service),
):
    """The options on the Payment screen.

    `requires_card` tells the client whether to show the card form next, which
    is the only branch in the design's payment flow.
    """
    data = service.list_methods()
    return GenericResponse(message=f"{len(data)} methods", data=data)


@router.post("/bookings/{booking_id}/pay",
             response_model=GenericResponse[Booking], tags=["payment"],
             summary="Pay for a booking and confirm the seats")
async def pay(
    *,
    service: payment_services.PaymentServices = Depends(payment_service),
    booking_id: str = Path(..., examples=["bkg_9f2a7c1e"]),
    payload: PaymentRequest = Body(...),
    idempotency_key: Optional[str] = Header(
        default=None, alias="Idempotency-Key",
        description="Send a unique value per payment attempt. Retrying with "
                    "the same key returns the original result instead of "
                    "charging again."),
    user: CurrentUser = Depends(get_current_user),
):
    """Take payment and turn the held seats into a permanent reservation.

    The steps run in this order on purpose:

    1. the booking is claimed atomically, so two simultaneous requests cannot
       both charge
    2. the seats are reserved, where a unique index makes double selling
       impossible whatever the lock believed
    3. only then is the card charged, because that is the step a refund would
       be needed to undo

    A seat lost between the summary and the payment screen therefore costs
    nothing: the request fails with **409** before any money moves.

    Send an **Idempotency-Key** header. A retry with the same key returns the
    original booking rather than charging twice, which matters on a mobile
    network where a response can be lost after the request succeeded.

    Card numbers are validated, used and discarded; only the last four digits
    are kept. For the simulated gateway, a card ending `0002` or `0000` is
    declined with **402** so the failure path can be exercised.
    """
    data = await service.pay(user, booking_id, payload, idempotency_key)
    return GenericResponse(
        message=f"Booking {data.reference} confirmed", data=data)


@router.get("/bookings/{booking_id}/ticket",
            response_model=GenericResponse[Ticket], tags=["payment"],
            summary="The ticket for a confirmed booking")
async def get_ticket(
    *,
    service: payment_services.PaymentServices = Depends(payment_service),
    booking_id: str = Path(..., examples=["bkg_9f2a7c1e"]),
    user: CurrentUser = Depends(get_current_user),
):
    """The View ticket screen shown after a successful booking.

    `qr_payload` carries the booking reference alone, so scanning it at the
    door is a lookup rather than a credential that could be forged from its
    contents.
    """
    data = await service.get_ticket(user, booking_id)
    return GenericResponse(message=f"Ticket {data.reference}", data=data)
