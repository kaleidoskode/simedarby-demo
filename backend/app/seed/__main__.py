"""Command line entry point for the seeder."""

import argparse
import asyncio

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.databases.mongodb import collections
from app.databases.mongodb.dependencies import get_mongo_db1, mongo_service
from app.schemas.common_schema import Money
from app.seed.seeder import (
    DEMO_MOVIE,
    DEMO_SEAT_PRICE_MINOR,
    WIREFRAME_TAKEN_SEATS,
    demo_showtime_id,
    seed,
)

configure_logging()


async def main(reset: bool) -> int:
    db = await get_mongo_db1()

    try:
        counts = await seed(db, reset=reset)

        # Read the names back from the database rather than restating them
        # here, so this summary cannot drift from what was actually written.
        showtime = demo_showtime_id()
        record = await db[collections.SHOWTIMES].find_one({"_id": showtime})
        movie = await db[collections.MOVIES].find_one({"_id": DEMO_MOVIE})
    finally:
        mongo_service.close()

    print("\nSeeded collections")
    print("-" * 46)
    for name in collections.ALL:
        print(f"  {name:<22} {counts.get(name, 0):>5}")

    print("\nDemo screening from the wireframe")
    print("-" * 46)
    print(f"  showtime_id   {showtime}")
    print(f"  movie         {movie['title'] if movie else '(missing)'}")
    if record:
        print(f"  cinema        {record['cinema_name']}")
        print(f"  when          {record['display_date']} "
              f"{record['display_time']} (Asia/Kuala_Lumpur)")
    print(f"  already sold  {', '.join(WIREFRAME_TAKEN_SEATS)}")

    # Reproduce the Booking Summary total so a drift in seed prices is caught
    # here rather than being noticed against the design later. The wireframe is
    # priced in naira; the same figures are used at Malaysian scale, so its
    # 10,450 minor units read as RM104.50.
    tickets = DEMO_SEAT_PRICE_MINOR * 2           # F4 and F5
    fnb = 5400                                    # Fresh XL Combo, discounted
    service = settings.service_charge_minor       # RM0.50
    total = tickets + fnb + service

    print("\nBooking Summary check (seats F4, F5 + Fresh XL Combo)")
    print("-" * 46)
    print(f"  Tickets        {Money.of(tickets, settings.currency).display:>10}")
    print(f"  Food & Bev     {Money.of(fnb, settings.currency).display:>10}")
    print(f"  Service charge {Money.of(service, settings.currency).display:>10}")
    print(f"  Total          {Money.of(total, settings.currency).display:>10}")

    expected = 10450
    if total == expected:
        print(f"\n  matches the wireframe breakdown, at "
              f"{Money.of(expected, settings.currency).display}")
        return 0

    print(f"\n  MISMATCH: expected {Money.of(expected, settings.currency).display}")
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the cinema booking data")
    parser.add_argument(
        "--reset", action="store_true",
        help="delete every document first, then reinsert")
    args = parser.parse_args()

    raise SystemExit(asyncio.run(main(args.reset)))
