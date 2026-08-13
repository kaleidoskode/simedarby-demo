"""Builds the demo dataset and writes it to MongoDB.

Static catalogue records live in data/*.json. Anything date dependent is
generated here relative to the run date, so the seed never goes stale: the
wireframe shows dates in November 2021, and screenings fixed to that month
would be filtered out as past by every showtime query.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.databases.mongodb import collections
from app.databases.mongodb.indexes import ensure_indexes

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

# The cinema's local timezone. Screenings are stored in UTC and rendered in
# local time, so a client in another timezone still sees the correct listing.
CINEMA_TZ = ZoneInfo("Asia/Kuala_Lumpur")

# Daily schedule, exactly the times on the Ticket Booking screen.
SCREENING_TIMES = ["09:20", "11:40", "13:20", "15:30", "17:40", "19:30", "21:20"]

DAYS_AHEAD = 7

# Seat price per screening, in minor units (sen). RM25.00 for the premium hall
# down to RM20.00, which is the usual range for a Malaysian cinema ticket.
DEMO_SEAT_PRICE_MINOR = 2500

# movie -> (cinema, hall, seat price in minor units). One movie per hall, so no
# two screenings ever occupy the same room at the same time.
SCHEDULE: List[Tuple[str, str, str, int]] = [
    ("mov_venom_carnage", "cin_gsc_midvalley", "hall_gsc_mv_1",
     DEMO_SEAT_PRICE_MINOR),
    ("mov_no_time_to_die", "cin_gsc_midvalley", "hall_gsc_mv_2", 2500),
    ("mov_shang_chi", "cin_tgv_sunway", "hall_tgv_sp_1", 2000),
    ("mov_mat_kilau", "cin_tgv_sunway", "hall_tgv_sp_2", 2000),
    ("mov_venom_carnage", "cin_gsc_gurney", "hall_gsc_gp_1", 2200),
]

# Seats marked with a cross on the wireframe seating plan. Seeded as a
# confirmed booking so they arrive through the ordinary reservation path
# rather than as a special case in the seat plan endpoint.
WIREFRAME_TAKEN_SEATS = [
    "B5", "B6",
    "C2", "C3",
    "D4", "D5",
    "E3", "E4", "E5", "E6", "E7",
]

DEMO_MOVIE = "mov_venom_carnage"
DEMO_CINEMA = "cin_gsc_midvalley"
DEMO_HALL = "hall_gsc_mv_1"
DEMO_TIME = "17:40"  # 5:40PM, the screening on the Booking Summary screen
DEMO_DAY_OFFSET = 1


def _load(name: str) -> List[Dict[str, Any]]:
    """Read a seed file, dropping the `comment` keys used for annotation."""
    with open(DATA_DIR / f"{name}.json", encoding="utf-8") as handle:
        records = json.load(handle)
    for record in records:
        record.pop("comment", None)
    return records


def _display_time(moment: datetime) -> str:
    """Render a UTC instant as local time in the wireframe's format."""
    local = moment.astimezone(CINEMA_TZ)
    return local.strftime("%I:%M%p").lstrip("0")


def build_showtimes(movies: List[Dict[str, Any]],
                    cinemas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate screenings for the next DAYS_AHEAD days."""
    durations = {m["_id"]: m["duration_mins"] for m in movies}
    cinema_names = {c["_id"]: c["name"] for c in cinemas}

    today_local = datetime.now(CINEMA_TZ).date()
    showtimes: List[Dict[str, Any]] = []

    for day in range(DAYS_AHEAD):
        date = today_local + timedelta(days=day)
        for movie_id, cinema_id, hall_id, price_minor in SCHEDULE:
            for clock in SCREENING_TIMES:
                hour, minute = (int(part) for part in clock.split(":"))
                starts_local = datetime(
                    date.year, date.month, date.day, hour, minute,
                    tzinfo=CINEMA_TZ)
                starts_at = starts_local.astimezone(timezone.utc)
                # Published end times are rounded up to the next five minutes,
                # which is how the Booking Summary in the design reaches 7:20PM
                # for a 5:40PM screening of a 1h37m film.
                raw_end = starts_at + timedelta(minutes=durations[movie_id])
                padding = (-raw_end.minute) % 5
                ends_at = (raw_end + timedelta(minutes=padding)).replace(
                    second=0, microsecond=0)

                showtimes.append({
                    "_id": (f"sho_{date:%Y%m%d}_{clock.replace(':', '')}"
                            f"_{hall_id.replace('hall_', '')}"),
                    "movie_id": movie_id,
                    "cinema_id": cinema_id,
                    "cinema_name": cinema_names[cinema_id],
                    "hall_id": hall_id,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "display_time": _display_time(starts_at),
                    "display_date": f"{date:%b %d, %Y}",
                    "price_minor": price_minor,
                    "currency": settings.currency,
                    "ticket_class": "Classic",
                    "format": "IMDb 3D",
                    "language": "English",
                })

    return showtimes


def demo_showtime_id() -> str:
    """The screening the wireframe depicts, used for the pre-booked seats."""
    date = datetime.now(CINEMA_TZ).date() + timedelta(days=DEMO_DAY_OFFSET)
    return (f"sho_{date:%Y%m%d}_{DEMO_TIME.replace(':', '')}"
            f"_{DEMO_HALL.replace('hall_', '')}")


def build_taken_seats(showtime_id: str,
                      price_minor: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Create the confirmed booking that owns the crossed-out seats."""
    now = datetime.now(timezone.utc)
    booking_id = "bkg_seeded_taken"
    tickets_minor = price_minor * len(WIREFRAME_TAKEN_SEATS)
    total_minor = tickets_minor + settings.service_charge_minor

    booking = {
        "_id": booking_id,
        "reference": "CBK-SEED01",
        "user_id": "usr_seed_patron",
        "showtime_id": showtime_id,
        "seats": WIREFRAME_TAKEN_SEATS,
        "status": "confirmed",
        "ticket_class": "Classic",
        "fnb_items": [],
        "amounts": {
            "tickets_minor": tickets_minor,
            "fnb_minor": 0,
            "service_charge_minor": settings.service_charge_minor,
            "total_minor": total_minor,
        },
        "currency": settings.currency,
        "payment": {
            "method": "debit_card",
            "status": "succeeded",
            "reference": "PAY-SEED0001",
            "card_last4": "4242",
            "paid_at": now,
        },
        "created_at": now,
        "expires_at": None,
        "confirmed_at": now,
    }

    reservations = [
        {
            "_id": f"res_seed_{showtime_id}_{seat}",
            "showtime_id": showtime_id,
            "seat": seat,
            "booking_id": booking_id,
            "user_id": "usr_seed_patron",
            "created_at": now,
        }
        for seat in WIREFRAME_TAKEN_SEATS
    ]

    return booking, reservations


async def seed(db: AsyncIOMotorDatabase, reset: bool = False) -> Dict[str, int]:
    """Populate the database. Returns the document count per collection."""
    if reset:
        for name in collections.ALL:
            await db[name].delete_many({})
        logger.info("Cleared %d collections", len(collections.ALL))

    await ensure_indexes(db)

    movies = _load("movies")
    cinemas = _load("cinemas")

    documents: Dict[str, List[Dict[str, Any]]] = {
        collections.MOVIES: movies,
        collections.LOCATIONS: _load("locations"),
        collections.CINEMAS: cinemas,
        collections.HALLS: _load("halls"),
        collections.FNB_ITEMS: _load("fnb_items"),
    }

    # Reviews carry a relative age so they stay recent.
    now = datetime.now(timezone.utc)
    reviews = _load("reviews")
    for review in reviews:
        review["created_at"] = now - timedelta(days=review.pop("days_ago"))
    documents[collections.REVIEWS] = reviews

    documents[collections.SHOWTIMES] = build_showtimes(movies, cinemas)

    showtime_id = demo_showtime_id()
    booking, reservations = build_taken_seats(
        showtime_id, DEMO_SEAT_PRICE_MINOR)
    documents[collections.BOOKINGS] = [booking]
    documents[collections.SEAT_RESERVATIONS] = reservations

    counts: Dict[str, int] = {}
    for name, records in documents.items():
        if not records:
            counts[name] = 0
            continue
        # Upsert by _id so re-running without --reset repairs rather than
        # duplicates or fails on the unique indexes.
        for record in records:
            await db[name].replace_one(
                {"_id": record["_id"]}, record, upsert=True)
        counts[name] = await db[name].count_documents({})

    return counts
