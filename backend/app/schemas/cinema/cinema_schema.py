"""Venue models: locations, cinemas, halls and showtimes."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.cinema.common_schema import Money


class Location(BaseModel):
    """A city the user picks from the Location dropdown."""

    id: str = Field(..., examples=["loc_kuala_lumpur"])
    name: str = Field(..., examples=["Kuala Lumpur"])
    country: str = Field(..., examples=["Malaysia"])


class CinemaSummary(BaseModel):
    """A cinema card, showing its ticket price range."""

    id: str = Field(..., examples=["cin_gsc_midvalley"])
    name: str = Field(..., examples=["GSC Mid Valley Megamall"])
    location_id: str = Field(..., examples=["loc_kuala_lumpur"])
    location_name: str = Field(..., examples=["Kuala Lumpur"])
    price_from: Money
    price_to: Money


class SeatRow(BaseModel):
    """One row of the physical seating layout.

    `seat_numbers` is explicit rather than a count because the front and back
    rows are inset: rows A and H carry numbers 2 to 7 while the rows between
    them carry 1 to 8, which is what produces the tapered shape in the design.
    """

    row: str = Field(..., examples=["F"])
    seat_numbers: List[int] = Field(..., examples=[[1, 2, 3, 4, 5, 6, 7, 8]])


class Hall(BaseModel):
    """A screening hall and its physical seat layout."""

    id: str = Field(..., examples=["hall_gsc_mv_1"])
    cinema_id: str = Field(..., examples=["cin_gsc_midvalley"])
    name: str = Field(..., examples=["Hall 1"])
    rows: List[SeatRow]
    total_seats: int = Field(..., examples=[60])


class ShowtimeSummary(BaseModel):
    """A single screening the user can book."""

    id: str = Field(..., examples=["sho_20260814_1740_gsc_mv_1"])
    movie_id: str
    cinema_id: str
    cinema_name: str = Field(..., examples=["GSC Mid Valley Megamall"])
    hall_id: str
    starts_at: datetime
    ends_at: datetime
    display_time: str = Field(..., description="Local time as shown in the UI",
                              examples=["5:40PM"])
    price: Money
    ticket_class: str = Field(..., examples=["Classic"])
    format: Optional[str] = Field(default=None, examples=["IMDb 3D"])
    language: Optional[str] = Field(default=None, examples=["English"])
