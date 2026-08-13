"""Index definitions and their bootstrap.

`ensure_indexes` runs on application startup. Creating an index that already
exists with the same definition is a no-op in MongoDB, so this is safe to call
on every boot and on every worker.
"""

import logging
from typing import Any, Dict, List, Tuple

import pymongo
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.databases.mongodb import collections

logger = logging.getLogger(__name__)


# collection -> list of (keys, options)
INDEXES: Dict[str, List[Tuple[List[Tuple[str, Any]], Dict[str, Any]]]] = {
    collections.MOVIES: [
        # Sort order for the catalogue listing. Search is a case-insensitive
        # substring match, which no index can serve, so a text index would only
        # have looked useful without being used; see CatalogServices._contains.
        ([("title", pymongo.ASCENDING)], {"name": "movie_title"}),
        ([("sections", pymongo.ASCENDING)], {"name": "movie_sections"}),
    ],
    collections.REVIEWS: [
        ([("movie_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
         {"name": "review_by_movie_recent"}),
    ],
    collections.CINEMAS: [
        ([("location_id", pymongo.ASCENDING)], {"name": "cinema_by_location"}),
    ],
    collections.HALLS: [
        ([("cinema_id", pymongo.ASCENDING)], {"name": "hall_by_cinema"}),
    ],
    collections.SHOWTIMES: [
        ([("movie_id", pymongo.ASCENDING), ("starts_at", pymongo.ASCENDING)],
         {"name": "showtime_by_movie_start"}),
        ([("cinema_id", pymongo.ASCENDING), ("starts_at", pymongo.ASCENDING)],
         {"name": "showtime_by_cinema_start"}),
    ],
    collections.FNB_ITEMS: [
        ([("category", pymongo.ASCENDING)], {"name": "fnb_by_category"}),
    ],
    collections.BOOKINGS: [
        ([("reference", pymongo.ASCENDING)],
         {"name": "uniq_booking_reference", "unique": True}),
        ([("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
         {"name": "booking_by_user_recent"}),
        ([("status", pymongo.ASCENDING), ("expires_at", pymongo.ASCENDING)],
         {"name": "booking_by_status_expiry"}),
    ],
    collections.SEAT_RESERVATIONS: [
        # The guarantee behind "first come first serve".
        #
        # A Redis lock stops two users reaching checkout for the same seat, but
        # a lock can be lost to a Redis restart or eviction. This unique index
        # is what makes a seat physically impossible to sell twice: the second
        # insert raises DuplicateKeyError inside the database itself, whatever
        # the application layer believed.
        ([("showtime_id", pymongo.ASCENDING), ("seat", pymongo.ASCENDING)],
         {"name": "uniq_showtime_seat", "unique": True}),
        ([("booking_id", pymongo.ASCENDING)],
         {"name": "reservation_by_booking"}),
    ],
}


async def ensure_indexes(db: AsyncIOMotorDatabase) -> Dict[str, List[str]]:
    """Create every declared index, returning what was ensured per collection."""
    created: Dict[str, List[str]] = {}

    for collection_name, definitions in INDEXES.items():
        names = []
        for keys, options in definitions:
            try:
                name = await db[collection_name].create_index(keys, **options)
                names.append(name)
            except Exception as exc:
                # A conflicting definition left over from an earlier schema
                # should be visible, not silently swallowed at startup.
                logger.error(
                    "Failed to create index %s on %s: %s",
                    options.get("name", keys), collection_name, exc)
                raise
        created[collection_name] = names

    logger.info("Ensured indexes on %d collections", len(created))
    return created
