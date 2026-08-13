"""Booking endpoints: the Booking Summary screen and the steps into it."""

import logging
from typing import List

from fastapi import APIRouter, Body, Depends, Path

from app.core.construct_services import bookings as booking_service
from app.core.security import get_current_user
from app.helpers.generic_response import GenericResponse
from app.schemas.auth_schema import CurrentUser
from app.schemas.booking_schema import Booking, BookingCreate, FnbSelection
from app.services import booking_services

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=GenericResponse[Booking], status_code=201,
             summary="Start a booking from held seats")
async def create_booking(
    *,
    service: booking_services.BookingServices = Depends(booking_service),
    payload: BookingCreate = Body(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Turn a held selection into a draft booking.

    The caller must already hold every seat, so a client cannot skip the
    seating plan and book seats it never locked. Returns **409** naming the
    seats it does not hold.

    Creating the booking extends those holds from the short seat-picking window
    to the longer checkout window, so the user does not lose their seats while
    reading the summary and paying. The booking's `expires_at` matches, and
    when it passes the seats are already free.
    """
    data = await service.create(user, payload.showtime_id, payload.seats)
    return GenericResponse(
        message=f"Booking {data.reference} created", data=data)


@router.get("", response_model=GenericResponse[List[Booking]],
            summary="List your bookings")
async def list_bookings(
    *,
    service: booking_services.BookingServices = Depends(booking_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Every booking belonging to the caller, newest first."""
    data = await service.list_mine(user)
    return GenericResponse(message=f"{len(data)} booking(s)", data=data)


@router.get("/{booking_id}", response_model=GenericResponse[Booking],
            summary="Booking summary")
async def get_booking(
    *,
    service: booking_services.BookingServices = Depends(booking_service),
    booking_id: str = Path(..., examples=["bkg_9f2a7c1e"]),
    user: CurrentUser = Depends(get_current_user),
):
    """Everything the Booking Summary screen renders.

    The screening details are carried on the booking itself, so the summary and
    the ticket come back in one call and still read correctly long after the
    catalogue has moved on.
    """
    data = await service.get(user, booking_id)
    return GenericResponse(message="Booking fetched", data=data)


@router.put("/{booking_id}/fnb", response_model=GenericResponse[Booking],
            summary="Set the food and beverage order")
async def set_fnb(
    *,
    service: booking_services.BookingServices = Depends(booking_service),
    booking_id: str = Path(..., examples=["bkg_9f2a7c1e"]),
    payload: FnbSelection = Body(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Attach food and drink to the booking and recompute the total.

    The whole order is replaced rather than added to, which matches a screen
    where quantities are adjusted then confirmed, and makes the call
    idempotent: sending it twice cannot double the order. A quantity of zero
    removes an item, and an empty list clears the order, which is what Skip
    does.

    Prices come from the catalogue, never from the request, so a client cannot
    choose what it pays.
    """
    data = await service.set_fnb(user, booking_id, payload.items)
    return GenericResponse(
        message=f"{len(data.fnb_items)} item(s), total {data.amounts.total.display}",
        data=data)


@router.delete("/{booking_id}", response_model=GenericResponse[Booking],
               summary="Cancel a booking and release its seats")
async def cancel_booking(
    *,
    service: booking_services.BookingServices = Depends(booking_service),
    booking_id: str = Path(..., examples=["bkg_9f2a7c1e"]),
    user: CurrentUser = Depends(get_current_user),
):
    """Abandon the booking and hand the seats straight back.

    The holds are released immediately and broadcast, so everyone watching that
    seating plan sees the seats reappear rather than waiting out the TTL that
    would eventually have freed them.
    """
    data = await service.cancel(user, booking_id)
    return GenericResponse(message=f"Booking {data.reference} cancelled",
                           data=data)
