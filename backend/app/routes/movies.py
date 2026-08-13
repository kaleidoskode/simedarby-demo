"""Movie catalogue endpoints: home screen, movie detail and reviews."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query

from app.core.config import settings
from app.core.construct_services import catalog
from app.helpers.generic_response import GenericResponse
from app.schemas.common_schema import MovieSection, Page
from app.schemas.movie_schema import (
    MovieDetail,
    MovieSummary,
    ReviewList,
)
from app.services import catalog_services

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=GenericResponse[Page[MovieSummary]],
            summary="List or search movies")
async def list_movies(
    *,
    service: catalog_services.CatalogServices = Depends(catalog),
    q: Optional[str] = Query(
        default=None,
        description="Search movie titles and synopses, case insensitive",
        examples=["venom"]),
    section: Optional[MovieSection] = Query(
        default=None,
        description="Home screen rail: new_release, popular or recommended"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=settings.default_page_size, ge=1,
                       le=settings.max_page_size),
):
    """Backs both the home screen rails and the search bar.

    Without `q` this is the catalogue; with it, the search results. `section`
    selects one of the home screen groupings.
    """
    data = await service.list_movies(q=q, section=section, page=page,
                                     limit=limit)
    return GenericResponse(
        message=f"Found {data.meta.total} movies", data=data)


@router.get("/{movie_id}", response_model=GenericResponse[MovieDetail],
            summary="Movie detail")
async def get_movie(
    *,
    service: catalog_services.CatalogServices = Depends(catalog),
    movie_id: str = Path(..., examples=["mov_venom_carnage"]),
):
    """Everything behind the Movie Details tab: synopsis, cast, crew, format."""
    data = await service.get_movie(movie_id)
    return GenericResponse(message="Movie fetched", data=data)


@router.get("/{movie_id}/reviews", response_model=GenericResponse[ReviewList],
            summary="Ratings and reviews for a movie")
async def list_reviews(
    *,
    service: catalog_services.CatalogServices = Depends(catalog),
    movie_id: str = Path(..., examples=["mov_venom_carnage"]),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=settings.default_page_size, ge=1,
                       le=settings.max_page_size),
):
    """The Ratings & Reviews tab.

    Returns the star breakdown for the bar chart alongside the reviews, since
    the screen renders both at once. The breakdown covers every review, not
    just the page being returned.
    """
    data = await service.list_reviews(movie_id, page=page, limit=limit)
    return GenericResponse(
        message=f"{data.breakdown.total} reviews", data=data)
