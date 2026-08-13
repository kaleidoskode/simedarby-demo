"""Venue and screening endpoints behind the Ticket Booking screen."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query

from app.core.construct_services import catalog
from app.helpers.generic_response import GenericResponse
from app.schemas.cinema_schema import (
    CinemaSummary,
    Hall,
    Location,
    ShowtimeSummary,
)
from app.services import catalog_services

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/locations", response_model=GenericResponse[List[Location]],
            tags=["venues"], summary="List locations")
async def list_locations(
    *, service: catalog_services.CatalogServices = Depends(catalog),
):
    """The Location dropdown on the Ticket Booking screen."""
    data = await service.list_locations()
    return GenericResponse(message=f"{len(data)} locations", data=data)


@router.get("/cinemas", response_model=GenericResponse[List[CinemaSummary]],
            tags=["venues"], summary="List cinemas")
async def list_cinemas(
    *,
    service: catalog_services.CatalogServices = Depends(catalog),
    location_id: Optional[str] = Query(default=None,
                                       examples=["loc_kuala_lumpur"]),
    q: Optional[str] = Query(default=None,
                             description="Search cinema names",
                             examples=["sunway"]),
):
    """The Cinema Hall dropdown, and the cinema half of the home search bar.

    Each cinema carries its ticket price range, which is what the two cards at
    the top of the Ticket Booking screen show.
    """
    data = await service.list_cinemas(location_id=location_id, q=q)
    return GenericResponse(message=f"{len(data)} cinemas", data=data)


@router.get("/halls/{hall_id}", response_model=GenericResponse[Hall],
            tags=["venues"], summary="Seat layout of a hall")
async def get_hall(
    *,
    service: catalog_services.CatalogServices = Depends(catalog),
    hall_id: str = Path(..., examples=["hall_gsc_mv_1"]),
):
    """The physical seat grid, before any availability is applied.

    Rows A and H are inset, which is what gives the seating plan its tapered
    shape. Live availability arrives with the seat plan endpoint.
    """
    data = await service.get_hall(hall_id)
    return GenericResponse(message="Hall fetched", data=data)


@router.get("/showtimes",
            response_model=GenericResponse[List[ShowtimeSummary]],
            tags=["showtimes"], summary="List screenings")
async def list_showtimes(
    *,
    service: catalog_services.CatalogServices = Depends(catalog),
    movie_id: Optional[str] = Query(default=None,
                                    examples=["mov_venom_carnage"]),
    cinema_id: Optional[str] = Query(default=None,
                                     examples=["cin_gsc_midvalley"]),
    date: Optional[str] = Query(
        default=None,
        description="Local calendar date, YYYY-MM-DD",
        examples=["2026-08-14"]),
    include_past: bool = Query(
        default=False,
        description="Include screenings that have already started"),
):
    """The Available Time buttons.

    `date` is the date as the user sees it on the date strip and is resolved in
    the cinema's timezone, so a screening late in the evening is not pushed
    into the next day by a UTC comparison.

    Screenings that have already started are excluded by default, since they
    cannot be booked.
    """
    data = await service.list_showtimes(
        movie_id=movie_id, cinema_id=cinema_id, date_text=date,
        include_past=include_past)
    return GenericResponse(message=f"{len(data)} showtimes", data=data)
