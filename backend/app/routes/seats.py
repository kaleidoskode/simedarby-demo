"""Seating plan and seat lock endpoints.

These are the endpoints behind the assignment's core scenario: a seat is held
the moment a user selects it, and every other user watching that plan is told.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, Path, Query
from fastapi.security import HTTPAuthorizationCredentials

from app.core.construct_services import seats as seat_service
from app.core.security import bearer_scheme, decode_token, get_current_user
from app.helpers.generic_response import GenericResponse
from app.schemas.auth_schema import CurrentUser
from app.schemas.seat_schema import (
    LockResult,
    ReleaseResult,
    SeatChangeList,
    SeatPlan,
    SeatSelection,
)
from app.services import seat_services

logger = logging.getLogger(__name__)

router = APIRouter()


async def optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[CurrentUser]:
    """Resolve the caller if a token is present, without demanding one.

    The seating plan is readable anonymously, matching a design that has no
    login. A token only changes the labelling: with one, the caller's own holds
    come back as `held_by_me` so they render as Selected rather than taken.
    """
    if credentials is None or not credentials.credentials:
        return None
    claims = decode_token(credentials.credentials)
    return CurrentUser(id=claims["sub"], name=claims.get("name", "Guest"))


@router.get("/{showtime_id}/seats", response_model=GenericResponse[SeatPlan],
            summary="Seating plan for a screening")
async def get_seat_plan(
    *,
    service: seat_services.SeatServices = Depends(seat_service),
    showtime_id: str = Path(..., examples=["sho_20260814_1740_gsc_mv_1"]),
    user: Optional[CurrentUser] = Depends(optional_user),
):
    """Every seat in the hall with its current state.

    A seat is `booked` (sold), `locked` (someone is choosing it) or
    `available`. `held_by_me` distinguishes the caller's own holds, which is
    what the design's Selected state needs.

    `version` is the position in the change log this plan reflects. Pass it
    back as `?since=` to receive only what has changed since.
    """
    data = await service.get_plan(showtime_id, viewer_id=user.id if user else "")
    return GenericResponse(
        message=f"{data.summary.available} of {data.summary.total} available",
        data=data)


@router.get("/{showtime_id}/seats/changes",
            response_model=GenericResponse[SeatChangeList],
            summary="Seat changes since a version (polling fallback)")
async def get_seat_changes(
    *,
    service: seat_services.SeatServices = Depends(seat_service),
    showtime_id: str = Path(..., examples=["sho_20260814_1740_gsc_mv_1"]),
    since: str = Query(
        ...,
        description="Version from a previous plan or change response",
        examples=["1723531200000-0"]),
    user: Optional[CurrentUser] = Depends(optional_user),
):
    """Only what changed, for clients that cannot hold a WebSocket open.

    This reads the same change log the WebSocket delivers, so the two
    transports can never disagree. It is also the reconnect path: after a
    dropped socket, pass the last version you saw to collect what was missed
    rather than re-fetching the whole plan.

    The response's `version` is the value to send as the next `since`. When
    nothing changed, it is echoed back unchanged and `changes` is empty.
    """
    data = await service.get_changes(showtime_id, since=since,
                                     viewer_id=user.id if user else "")
    return GenericResponse(
        message=f"{len(data.changes)} change(s) since {since}", data=data)


@router.post("/{showtime_id}/seats/lock",
             response_model=GenericResponse[LockResult], status_code=201,
             summary="Hold seats on a first come first serve basis")
async def lock_seats(
    *,
    service: seat_services.SeatServices = Depends(seat_service),
    showtime_id: str = Path(..., examples=["sho_20260814_1740_gsc_mv_1"]),
    payload: SeatSelection = Body(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Claim seats for this caller.

    All or nothing: asking for F4 and F5 when F5 is taken holds neither, so a
    user never ends up with half a selection.

    The hold expires by itself after `ttl_seconds`, so closing the app frees
    the seats with nothing to clean up. Send a heartbeat to keep it alive while
    the user is still choosing.

    Returns **409** when any seat is already held or sold, with `details.conflicts`
    naming exactly which, so the client can repaint those seats rather than
    reloading the whole plan.
    """
    data = await service.lock(showtime_id, payload.seats, user.id)
    return GenericResponse(message=f"Holding {', '.join(data.seats)}",
                           data=data)


@router.delete("/{showtime_id}/seats/lock",
               response_model=GenericResponse[ReleaseResult],
               summary="Release held seats")
async def release_seats(
    *,
    service: seat_services.SeatServices = Depends(seat_service),
    showtime_id: str = Path(..., examples=["sho_20260814_1740_gsc_mv_1"]),
    payload: SeatSelection = Body(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Give seats back, for example on Cancel or when deselecting one.

    Only the caller's own holds are released. Seats held by someone else are
    reported in `ignored` and left untouched, so one user can never free
    another's selection.
    """
    data = await service.release(showtime_id, payload.seats, user.id)
    return GenericResponse(
        message=f"Released {len(data.released)} seat(s)", data=data)


@router.post("/{showtime_id}/seats/lock/heartbeat",
             response_model=GenericResponse[LockResult],
             summary="Extend a hold while the user is still choosing")
async def heartbeat(
    *,
    service: seat_services.SeatServices = Depends(seat_service),
    showtime_id: str = Path(..., examples=["sho_20260814_1740_gsc_mv_1"]),
    payload: SeatSelection = Body(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Push the expiry out on seats this caller still holds.

    A seat whose hold already lapsed is not revived, because it may belong to
    someone else by now. The response lists the seats still held, so an empty
    `seats` array means the selection was lost and the client should refresh
    the plan.
    """
    data = await service.heartbeat(showtime_id, payload.seats, user.id)
    return GenericResponse(
        message=f"{len(data.seats)} seat(s) still held", data=data)
