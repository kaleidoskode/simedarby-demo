"""Seating plan and seat lock models."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_schema import Money, SeatStatus


class SeatState(BaseModel):
    """One seat on the plan.

    `status` is what the seat is; `held_by_me` is who holds it. The design's
    legend needs both: a locked seat renders as "Selected" when it is the
    caller's own hold and as unavailable when it belongs to someone else.
    """

    seat: str = Field(..., examples=["F4"])
    row: str = Field(..., examples=["F"])
    number: int = Field(..., examples=[4])
    status: SeatStatus
    held_by_me: bool = False


class SeatPlanRow(BaseModel):
    """A row of the seating plan, in seat order."""

    row: str = Field(..., examples=["F"])
    seats: List[SeatState]


class SeatPlanSummary(BaseModel):
    """Counts for the plan, so the client does not have to tally them."""

    total: int = Field(..., examples=[60])
    available: int = Field(..., examples=[47])
    locked: int = Field(..., examples=[2])
    booked: int = Field(..., examples=[11])


class SeatPlan(BaseModel):
    """The Select Seat screen."""

    showtime_id: str = Field(..., examples=["sho_20260814_1740_gsc_mv_1"])
    hall_id: str = Field(..., examples=["hall_gsc_mv_1"])
    hall_name: str = Field(..., examples=["Hall 1"])
    price: Money
    rows: List[SeatPlanRow]
    summary: SeatPlanSummary
    version: str = Field(
        ...,
        description="Event stream position this plan reflects. Pass it back as "
                    "?since= to fetch only what changed.",
        examples=["1723531200000-0"])


class SeatSelection(BaseModel):
    """Body for locking, releasing or extending a hold."""

    seats: List[str] = Field(..., min_length=1, examples=[["F4", "F5"]])

    @field_validator("seats")
    @classmethod
    def normalise(cls, seats: List[str]) -> List[str]:
        """Upper-case, trim and de-duplicate while preserving order.

        De-duplication matters: ["F4", "F4"] would otherwise pass the same key
        to the lock script twice and inflate the seat count against the
        per-booking limit.
        """
        seen = []
        for seat in seats:
            cleaned = seat.strip().upper()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        if not seen:
            raise ValueError("At least one seat is required")
        return seen


class LockResult(BaseModel):
    """Outcome of a successful lock or extension."""

    showtime_id: str
    seats: List[str] = Field(..., examples=[["F4", "F5"]])
    holder: str = Field(..., examples=["usr_8f2a7c1e"])
    ttl_seconds: int = Field(..., examples=[120])
    expires_at: datetime = Field(
        ...,
        description="When the hold lapses unless extended by a heartbeat")


class SeatChange(BaseModel):
    """One seat changing state.

    The holder's id is deliberately not exposed. Whether a change is the
    caller's own is answered by `held_by_me`, computed per recipient, so
    watching a seating plan never reveals other people's identifiers.
    """

    seat: str = Field(..., examples=["F4"])
    status: SeatStatus
    held_by_me: bool = False
    at: datetime


class SeatChangeList(BaseModel):
    """Everything that happened after a given version."""

    showtime_id: str
    version: str = Field(
        ...,
        description="Position after applying these changes. Pass it as the "
                    "next ?since= value.",
        examples=["1723531200000-5"])
    changes: List[SeatChange]


class ReleaseResult(BaseModel):
    """Outcome of releasing a hold."""

    showtime_id: str
    released: List[str] = Field(
        ..., description="Seats that were held by the caller and are now free",
        examples=[["F4", "F5"]])
    ignored: List[str] = Field(
        default_factory=list,
        description="Seats the caller did not hold, so nothing was released",
        examples=[[]])
