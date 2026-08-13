"""Read side of the booking flow: movies, reviews, venues and screenings.

Everything here is a query. No state is held between calls, so these endpoints
can be served by any worker and cached at the edge if wanted.
"""

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.databases.mongodb import collections
from app.middleware.exception import CustomErrorException
from app.schemas.cinema_schema import (
    CinemaSummary,
    Hall,
    Location,
    SeatRow,
    ShowtimeSummary,
)
from app.schemas.common_schema import Money, Page, PageMeta
from app.schemas.fnb_schema import FnbItem
from app.schemas.movie_schema import (
    MovieDetail,
    MovieSummary,
    RatingBreakdown,
    Review,
    ReviewList,
)

logger = logging.getLogger(__name__)


class CatalogServices:
    """Queries backing the home, movie detail and ticket booking screens."""

    def __init__(self, mongo_db1: AsyncIOMotorDatabase):
        self.db = mongo_db1
        self.tz = ZoneInfo(settings.cinema_timezone)

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _page_meta(page: int, limit: int, total: int) -> PageMeta:
        return PageMeta(
            page=page,
            limit=limit,
            total=total,
            total_pages=math.ceil(total / limit) if limit else 0,
        )

    def _money(self, minor: Optional[int], currency: Optional[str] = None) -> Money:
        return Money.of(minor or 0, currency or settings.currency)

    @staticmethod
    def _contains(term: str) -> Dict[str, str]:
        """Case-insensitive substring match.

        `re.escape` is essential: the term comes straight from a search box, so
        an unescaped `(` or `*` would either raise or turn into an expensive
        pattern.

        A substring match cannot use an index, which is why the movies text
        index was dropped in favour of a plain one. That is the right trade for
        a catalogue of this size, where a collection scan is trivial; at a
        scale where it is not, this belongs in a dedicated search engine rather
        than a cleverer Mongo query.
        """
        return {"$regex": re.escape(term.strip()), "$options": "i"}

    # ----------------------------------------------------------------- movies

    def _to_summary(self, doc: Dict[str, Any]) -> MovieSummary:
        return MovieSummary(
            id=doc["_id"],
            title=doc["title"],
            poster_url=doc.get("poster_url"),
            genres=doc.get("genres", []),
            duration_mins=doc["duration_mins"],
            certification=doc["certification"],
            rating_avg=doc.get("rating_avg", 0.0),
            rating_count=doc.get("rating_count", 0),
            sections=doc.get("sections", []),
        )

    async def list_movies(self, q: Optional[str], section: Optional[str],
                          page: int, limit: int) -> Page[MovieSummary]:
        """Home screen rails and search results."""
        query: Dict[str, Any] = {"is_active": True}

        if q:
            contains = self._contains(q)
            query["$or"] = [{"title": contains}, {"synopsis": contains}]
        if section:
            query["sections"] = section

        total = await self.db[collections.MOVIES].count_documents(query)
        cursor = (self.db[collections.MOVIES]
                  .find(query)
                  .sort("title", 1)
                  .skip((page - 1) * limit)
                  .limit(limit))

        items = [self._to_summary(doc) async for doc in cursor]
        return Page[MovieSummary](
            items=items, meta=self._page_meta(page, limit, total))

    async def get_movie(self, movie_id: str) -> MovieDetail:
        """Movie detail screen."""
        doc = await self.db[collections.MOVIES].find_one({"_id": movie_id})
        if not doc:
            raise CustomErrorException(
                f"Movie '{movie_id}' not found", status_code=404)

        return MovieDetail(
            **self._to_summary(doc).model_dump(),
            synopsis=doc["synopsis"],
            trailer_url=doc.get("trailer_url"),
            release_date=doc["release_date"],
            casts=doc.get("casts", []),
            director=doc.get("director"),
            writers=doc.get("writers", []),
            formats=doc.get("formats", []),
        )

    async def list_reviews(self, movie_id: str, page: int,
                           limit: int) -> ReviewList:
        """Ratings & Reviews tab: the star breakdown plus a page of reviews."""
        if not await self.db[collections.MOVIES].find_one(
                {"_id": movie_id}, {"_id": 1}):
            raise CustomErrorException(
                f"Movie '{movie_id}' not found", status_code=404)

        query = {"movie_id": movie_id}

        # The bar chart needs every star bucket, including the ones with no
        # reviews, so it is aggregated in the database rather than counted from
        # the current page.
        pipeline = [
            {"$match": query},
            {"$group": {"_id": "$stars", "count": {"$sum": 1}}},
        ]
        counts = {star: 0 for star in range(1, 6)}
        total = 0
        weighted = 0
        async for row in self.db[collections.REVIEWS].aggregate(pipeline):
            counts[row["_id"]] = row["count"]
            total += row["count"]
            weighted += row["_id"] * row["count"]

        cursor = (self.db[collections.REVIEWS]
                  .find(query)
                  .sort("created_at", -1)
                  .skip((page - 1) * limit)
                  .limit(limit))

        items = [
            Review(
                id=doc["_id"],
                movie_id=doc["movie_id"],
                author=doc["author"],
                stars=doc["stars"],
                title=doc["title"],
                body=doc["body"],
                created_at=doc["created_at"],
            )
            async for doc in cursor
        ]

        return ReviewList(
            breakdown=RatingBreakdown(
                average=round(weighted / total, 1) if total else 0.0,
                total=total,
                counts=counts,
            ),
            items=items,
            meta=self._page_meta(page, limit, total),
        )

    # ----------------------------------------------------------------- venues

    async def list_locations(self) -> List[Location]:
        """The Location dropdown."""
        cursor = self.db[collections.LOCATIONS].find().sort("name", 1)
        return [
            Location(id=doc["_id"], name=doc["name"], country=doc["country"])
            async for doc in cursor
        ]

    async def list_cinemas(self, location_id: Optional[str],
                           q: Optional[str]) -> List[CinemaSummary]:
        """The Cinema Hall dropdown, optionally narrowed by location or name."""
        query: Dict[str, Any] = {"is_active": True}
        if location_id:
            query["location_id"] = location_id
        if q:
            query["name"] = self._contains(q)

        locations = {
            doc["_id"]: doc["name"]
            async for doc in self.db[collections.LOCATIONS].find()
        }

        cursor = self.db[collections.CINEMAS].find(query).sort("name", 1)
        return [
            CinemaSummary(
                id=doc["_id"],
                name=doc["name"],
                location_id=doc["location_id"],
                location_name=locations.get(doc["location_id"], "Unknown"),
                price_from=self._money(doc["price_from_minor"],
                                       doc.get("currency")),
                price_to=self._money(doc["price_to_minor"],
                                     doc.get("currency")),
            )
            async for doc in cursor
        ]

    async def get_hall(self, hall_id: str) -> Hall:
        """The physical seat layout of a hall."""
        doc = await self.db[collections.HALLS].find_one({"_id": hall_id})
        if not doc:
            raise CustomErrorException(
                f"Hall '{hall_id}' not found", status_code=404)

        return Hall(
            id=doc["_id"],
            cinema_id=doc["cinema_id"],
            name=doc["name"],
            rows=[SeatRow(**row) for row in doc["rows"]],
            total_seats=doc["total_seats"],
        )

    # -------------------------------------------------------------- showtimes

    def _day_bounds(self, date_text: str):
        """Turn a local calendar date into a UTC half-open interval.

        The client sends a date as the user sees it on the date strip. A day in
        Kuala Lumpur is not a day in UTC, so filtering on the raw string would
        include or drop the screenings either side of midnight.
        """
        try:
            day = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError as exc:
            raise CustomErrorException(
                f"Invalid date '{date_text}', expected YYYY-MM-DD",
                status_code=422) from exc

        start_local = datetime(day.year, day.month, day.day, tzinfo=self.tz)
        return (start_local.astimezone(timezone.utc),
                (start_local + timedelta(days=1)).astimezone(timezone.utc))

    async def list_showtimes(self, movie_id: Optional[str],
                             cinema_id: Optional[str],
                             date_text: Optional[str],
                             include_past: bool = False
                             ) -> List[ShowtimeSummary]:
        """The Available Time buttons for a movie, cinema and date."""
        query: Dict[str, Any] = {}
        if movie_id:
            query["movie_id"] = movie_id
        if cinema_id:
            query["cinema_id"] = cinema_id

        window: Dict[str, Any] = {}
        if date_text:
            start, end = self._day_bounds(date_text)
            window["$gte"] = start
            window["$lt"] = end
        if not include_past:
            # A screening that has already started cannot be booked, so the
            # lower bound is whichever is later: the requested day or now.
            now = datetime.now(timezone.utc)
            window["$gte"] = max(window["$gte"], now) if "$gte" in window else now
        if window:
            query["starts_at"] = window

        cursor = self.db[collections.SHOWTIMES].find(query).sort("starts_at", 1)
        return [
            ShowtimeSummary(
                id=doc["_id"],
                movie_id=doc["movie_id"],
                cinema_id=doc["cinema_id"],
                cinema_name=doc["cinema_name"],
                hall_id=doc["hall_id"],
                starts_at=doc["starts_at"],
                ends_at=doc["ends_at"],
                display_time=doc["display_time"],
                price=self._money(doc["price_minor"], doc.get("currency")),
                ticket_class=doc.get("ticket_class", "Classic"),
                format=doc.get("format"),
                language=doc.get("language"),
            )
            async for doc in cursor
        ]

    async def get_showtime(self, showtime_id: str) -> Dict[str, Any]:
        """Raw showtime document, used by the seat and booking services."""
        doc = await self.db[collections.SHOWTIMES].find_one(
            {"_id": showtime_id})
        if not doc:
            raise CustomErrorException(
                f"Showtime '{showtime_id}' not found", status_code=404)
        return doc

    # -------------------------------------------------------------------- F&B

    async def list_fnb(self, category: Optional[str]) -> List[FnbItem]:
        """The Beverages & Food tabs."""
        query: Dict[str, Any] = {}
        if category:
            query["category"] = category

        cursor = self.db[collections.FNB_ITEMS].find(query).sort("name", 1)
        return [
            FnbItem(
                id=doc["_id"],
                category=doc["category"],
                name=doc["name"],
                description=doc["description"],
                image_url=doc.get("image_url"),
                price=self._money(doc["price_minor"]),
                original_price=(self._money(doc["original_price_minor"])
                                if doc.get("original_price_minor") else None),
                discount_pct=doc.get("discount_pct"),
                is_available=doc.get("is_available", True),
            )
            async for doc in cursor
        ]
