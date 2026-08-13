"""Rendering instants in the cinema's local time.

Screenings are stored in UTC and shown in the timezone of the cinema, so a
client in another timezone still sees the listing the box office would print.
The formatting lives here rather than being repeated wherever it is needed, so
the seeder and the API cannot drift into showing different strings for the same
moment.
"""

from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import settings


@lru_cache(maxsize=4)
def cinema_timezone() -> ZoneInfo:
    """The cinema's timezone, resolved once and cached."""
    return ZoneInfo(settings.cinema_timezone)


def display_time(moment: datetime) -> str:
    """Format an instant as local clock time, e.g. "5:40PM"."""
    return moment.astimezone(cinema_timezone()).strftime("%I:%M%p").lstrip("0")


def display_date(moment: datetime) -> str:
    """Format an instant as a local calendar date, e.g. "Aug 14, 2026"."""
    return moment.astimezone(cinema_timezone()).strftime("%b %d, %Y")
