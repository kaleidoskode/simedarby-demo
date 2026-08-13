"""Canonical MongoDB collection names.

Referenced through these constants rather than as string literals so a rename
is a single edit and a typo is an import error instead of a silently empty
query result.
"""

MOVIES = "movies"
REVIEWS = "reviews"
LOCATIONS = "locations"
CINEMAS = "cinemas"
HALLS = "halls"
SHOWTIMES = "showtimes"
FNB_ITEMS = "fnb_items"
BOOKINGS = "bookings"
SEAT_RESERVATIONS = "seat_reservations"

ALL = (
    MOVIES,
    REVIEWS,
    LOCATIONS,
    CINEMAS,
    HALLS,
    SHOWTIMES,
    FNB_ITEMS,
    BOOKINGS,
    SEAT_RESERVATIONS,
)
