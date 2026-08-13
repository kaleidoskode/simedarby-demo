"""Movie catalogue models: the home screen, movie detail and reviews."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.cinema.common_schema import MovieSection


class MovieSummary(BaseModel):
    """Card shown in the home screen rails and in search results."""

    id: str = Field(..., examples=["mov_venom_carnage"])
    title: str = Field(..., examples=["Venom: Let There Be Carnage"])
    poster_url: Optional[str] = None
    genres: List[str] = Field(default_factory=list,
                              examples=[["Action", "Adventure", "Sci-fi"]])
    duration_mins: int = Field(..., examples=[97])
    certification: str = Field(..., examples=["15+"])
    rating_avg: float = Field(..., ge=0, le=5, examples=[4.0])
    rating_count: int = Field(..., ge=0, examples=[20])
    sections: List[MovieSection] = Field(default_factory=list)


class MovieDetail(MovieSummary):
    """Full record behind the movie detail screen."""

    synopsis: str = Field(..., examples=[
        "Eddie Brock is still struggling to co-exist with the shape-shifting "
        "extraterrestrial Venom."])
    trailer_url: Optional[str] = None
    release_date: str = Field(..., description="Month of release",
                              examples=["October 2021"])
    casts: List[str] = Field(default_factory=list)
    director: Optional[str] = None
    writers: List[str] = Field(default_factory=list)
    formats: List[str] = Field(default_factory=list,
                               examples=[["English", "IMDb 3D"]])


class Review(BaseModel):
    """A single customer review."""

    id: str
    movie_id: str
    author: str = Field(..., examples=["Adeola O."])
    stars: int = Field(..., ge=1, le=5, examples=[4])
    title: str = Field(..., examples=["INTERESTING MOVIE!"])
    body: str
    created_at: datetime


class RatingBreakdown(BaseModel):
    """Star distribution behind the ratings bar chart.

    Keys are the star values 1 to 5, values are how many reviews gave that
    score, so the client can draw the bars without counting client side.
    """

    average: float = Field(..., ge=0, le=5, examples=[4.0])
    total: int = Field(..., ge=0, examples=[20])
    counts: dict[int, int] = Field(
        ..., examples=[{5: 8, 4: 6, 3: 4, 2: 2, 1: 0}])
