"""The booking draft: seats held, food added, totals recomputed.

The arithmetic is checked against the Booking Summary in the wireframe, which
comes to RM104.50 for two seats and a discounted combo.
"""

import asyncio

TICKET_MINOR = 2500      # RM25.00 a seat at the demo cinema
COMBO = "fnb_fresh_xl_combo"
COMBO_MINOR = 5400       # RM54.00, discounted from RM60.00
SERVICE_MINOR = 50       # RM0.50


async def _hold(api, auth_header, showtime_id, tokens, seats):
    """Lock seats and return the response."""
    return await api.post(f"/showtimes/{showtime_id}/seats/lock",
                          json={"seats": seats}, headers=auth_header(tokens))


async def test_booking_requires_the_seats_to_be_held(
        api, token, auth_header, showtime_id, free_seats):
    """A client cannot book seats it never locked."""
    user = await token("user-1")

    response = await api.post("/bookings",
                              json={"showtime_id": showtime_id,
                                    "seats": [free_seats[0]]},
                              headers=auth_header(user))

    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "not_held"


async def test_cannot_book_seats_held_by_someone_else(
        api, token, auth_header, showtime_id, free_seats):
    """Holding is per user, so another user's hold does not count."""
    seat = free_seats[0]
    user1, user2 = await asyncio.gather(token("user-1"), token("user-2"))

    await _hold(api, auth_header, showtime_id, user1, [seat])

    response = await api.post("/bookings",
                              json={"showtime_id": showtime_id,
                                    "seats": [seat]},
                              headers=auth_header(user2))

    assert response.status_code == 409
    assert response.json()["details"]["conflicts"] == [seat]


async def test_creating_a_booking_matches_the_wireframe_ticket_total(
        api, token, auth_header, showtime_id, free_seats):
    """Two seats, no food yet: tickets plus the service charge."""
    seats = free_seats[:2]
    user = await token("user-1")
    await _hold(api, auth_header, showtime_id, user, seats)

    response = await api.post("/bookings",
                              json={"showtime_id": showtime_id,
                                    "seats": seats},
                              headers=auth_header(user))

    assert response.status_code == 201
    booking = response.json()["data"]

    assert booking["status"] == "draft"
    assert booking["seats"] == seats
    assert booking["reference"].startswith("CBK-")
    assert booking["amounts"]["tickets"]["minor"] == TICKET_MINOR * 2
    assert booking["amounts"]["fnb"]["minor"] == 0
    assert booking["amounts"]["service_charge"]["minor"] == SERVICE_MINOR
    assert booking["amounts"]["total"]["minor"] == (
        TICKET_MINOR * 2 + SERVICE_MINOR)
    assert booking["amounts"]["total"]["display"] == "RM50.50"


async def test_adding_the_combo_reaches_the_wireframe_total(
        api, token, auth_header, showtime_id, free_seats):
    """Two seats plus one Fresh XL Combo is RM104.50, as in the design."""
    seats = free_seats[:2]
    user = await token("user-1")
    await _hold(api, auth_header, showtime_id, user, seats)

    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id,
                                   "seats": seats},
                             headers=auth_header(user))
    booking_id = created.json()["data"]["id"]

    response = await api.put(
        f"/bookings/{booking_id}/fnb",
        json={"items": [{"fnb_id": COMBO, "quantity": 1}]},
        headers=auth_header(user))

    assert response.status_code == 200
    booking = response.json()["data"]
    amounts = booking["amounts"]

    assert amounts["tickets"]["display"] == "RM50.00"
    assert amounts["fnb"]["display"] == "RM54.00"
    assert amounts["service_charge"]["display"] == "RM0.50"
    assert amounts["total"]["display"] == "RM104.50"
    assert amounts["total"]["minor"] == (
        TICKET_MINOR * 2 + COMBO_MINOR + SERVICE_MINOR)

    line = booking["fnb_items"][0]
    assert line["name"] == "Fresh XL Combo"
    assert line["quantity"] == 1
    assert line["unit_price"]["minor"] == COMBO_MINOR


async def test_setting_food_replaces_rather_than_appends(
        api, token, auth_header, showtime_id, free_seats):
    """Sending the order twice must not double it."""
    seats = free_seats[:1]
    user = await token("user-1")
    await _hold(api, auth_header, showtime_id, user, seats)
    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id, "seats": seats},
                             headers=auth_header(user))
    booking_id = created.json()["data"]["id"]

    order = {"items": [{"fnb_id": COMBO, "quantity": 2}]}
    first = await api.put(f"/bookings/{booking_id}/fnb", json=order,
                          headers=auth_header(user))
    second = await api.put(f"/bookings/{booking_id}/fnb", json=order,
                           headers=auth_header(user))

    assert first.json()["data"]["amounts"]["fnb"]["minor"] == COMBO_MINOR * 2
    assert second.json()["data"]["amounts"]["fnb"]["minor"] == COMBO_MINOR * 2
    assert len(second.json()["data"]["fnb_items"]) == 1


async def test_an_empty_order_clears_the_food(
        api, token, auth_header, showtime_id, free_seats):
    """Skip on the food screen removes any earlier selection."""
    seats = free_seats[:1]
    user = await token("user-1")
    await _hold(api, auth_header, showtime_id, user, seats)
    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id, "seats": seats},
                             headers=auth_header(user))
    booking_id = created.json()["data"]["id"]

    await api.put(f"/bookings/{booking_id}/fnb",
                  json={"items": [{"fnb_id": COMBO, "quantity": 1}]},
                  headers=auth_header(user))
    cleared = await api.put(f"/bookings/{booking_id}/fnb", json={"items": []},
                            headers=auth_header(user))

    booking = cleared.json()["data"]
    assert booking["fnb_items"] == []
    assert booking["amounts"]["fnb"]["minor"] == 0
    assert booking["amounts"]["total"]["minor"] == TICKET_MINOR + SERVICE_MINOR


async def test_quantity_zero_removes_an_item(
        api, token, auth_header, showtime_id, free_seats):
    """The minus button reaching zero drops the line."""
    seats = free_seats[:1]
    user = await token("user-1")
    await _hold(api, auth_header, showtime_id, user, seats)
    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id, "seats": seats},
                             headers=auth_header(user))
    booking_id = created.json()["data"]["id"]

    response = await api.put(
        f"/bookings/{booking_id}/fnb",
        json={"items": [{"fnb_id": COMBO, "quantity": 0}]},
        headers=auth_header(user))

    assert response.json()["data"]["fnb_items"] == []


async def test_unknown_food_item_is_rejected(
        api, token, auth_header, showtime_id, free_seats):
    seats = free_seats[:1]
    user = await token("user-1")
    await _hold(api, auth_header, showtime_id, user, seats)
    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id, "seats": seats},
                             headers=auth_header(user))
    booking_id = created.json()["data"]["id"]

    response = await api.put(
        f"/bookings/{booking_id}/fnb",
        json={"items": [{"fnb_id": "fnb_nope", "quantity": 1}]},
        headers=auth_header(user))

    assert response.status_code == 422
    assert response.json()["details"]["unknown_items"] == ["fnb_nope"]


async def test_an_unavailable_item_is_rejected(
        api, token, auth_header, showtime_id, free_seats):
    """The seeded sold-out drink cannot be ordered."""
    seats = free_seats[:1]
    user = await token("user-1")
    await _hold(api, auth_header, showtime_id, user, seats)
    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id, "seats": seats},
                             headers=auth_header(user))
    booking_id = created.json()["data"]["id"]

    response = await api.put(
        f"/bookings/{booking_id}/fnb",
        json={"items": [{"fnb_id": "fnb_iced_coffee", "quantity": 1}]},
        headers=auth_header(user))

    assert response.status_code == 409
    assert response.json()["details"]["unavailable_items"] == [
        "fnb_iced_coffee"]


async def test_booking_carries_the_screening_details(
        api, token, auth_header, showtime_id, free_seats):
    """The summary renders from the booking alone, with no extra lookups."""
    seats = free_seats[:2]
    user = await token("user-1")
    await _hold(api, auth_header, showtime_id, user, seats)

    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id, "seats": seats},
                             headers=auth_header(user))
    screening = created.json()["data"]["screening"]

    assert screening["movie_title"] == "Venom: Let There Be Carnage"
    assert screening["cinema_name"] == "GSC Mid Valley Megamall"
    assert screening["hall_name"] == "Hall 1"
    assert screening["start_display"] == "5:40PM"
    assert screening["end_display"] == "7:20PM"
    assert screening["duration_mins"] == 97


async def test_creating_a_booking_extends_the_hold_to_checkout(
        api, token, auth_header, showtime_id, free_seats, redis):
    """The seat-picking TTL becomes the longer checkout window."""
    seat = free_seats[0]
    user = await token("user-1")
    await _hold(api, auth_header, showtime_id, user, [seat])

    key = f"lock:{showtime_id}:{seat}"
    before = await redis.ttl(key)
    assert before <= 120

    await api.post("/bookings",
                   json={"showtime_id": showtime_id, "seats": [seat]},
                   headers=auth_header(user))

    after = await redis.ttl(key)
    assert after > 120, f"hold was not extended: {before}s -> {after}s"


async def test_cancelling_releases_the_seats_immediately(
        api, token, auth_header, showtime_id, free_seats):
    """Cancel hands the seats back rather than waiting out the TTL."""
    seat = free_seats[0]
    user1, user2 = await asyncio.gather(token("user-1"), token("user-2"))
    await _hold(api, auth_header, showtime_id, user1, [seat])

    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id, "seats": [seat]},
                             headers=auth_header(user1))
    booking_id = created.json()["data"]["id"]

    blocked = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                             json={"seats": [seat]}, headers=auth_header(user2))
    assert blocked.status_code == 409

    cancelled = await api.delete(f"/bookings/{booking_id}",
                                 headers=auth_header(user1))
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"

    now_free = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                              json={"seats": [seat]},
                              headers=auth_header(user2))
    assert now_free.status_code == 201


async def test_cancelling_is_broadcast_to_watchers(
        api, token, auth_header, showtime_id, free_seats):
    """Other users see the seat reappear without polling the whole plan."""
    seat = free_seats[0]
    user = await token("user-1")
    await _hold(api, auth_header, showtime_id, user, [seat])
    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id, "seats": [seat]},
                             headers=auth_header(user))

    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    version = plan.json()["data"]["version"]

    await api.delete(f"/bookings/{created.json()['data']['id']}",
                     headers=auth_header(user))

    changes = await api.get(f"/showtimes/{showtime_id}/seats/changes",
                            params={"since": version})
    published = changes.json()["data"]["changes"]
    assert {"seat": seat, "status": "available"} in [
        {"seat": c["seat"], "status": c["status"]} for c in published]


async def test_another_user_cannot_read_your_booking(
        api, token, auth_header, showtime_id, free_seats):
    """Someone else's booking reads as missing, not as forbidden."""
    seats = free_seats[:1]
    user1, user2 = await asyncio.gather(token("user-1"), token("user-2"))
    await _hold(api, auth_header, showtime_id, user1, seats)
    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id, "seats": seats},
                             headers=auth_header(user1))
    booking_id = created.json()["data"]["id"]

    response = await api.get(f"/bookings/{booking_id}",
                             headers=auth_header(user2))
    assert response.status_code == 404


async def test_seat_limit_cannot_be_beaten_by_locking_twice(
        api, token, auth_header, showtime_id, free_seats):
    """The cap is on what a caller ends up holding, not on one request.

    Counting per request let a user take ten seats, then ten more, and book all
    twenty.
    """
    user = await token("greedy")

    first = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                           json={"seats": free_seats[:10]},
                           headers=auth_header(user))
    assert first.status_code == 201

    second = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                            json={"seats": free_seats[10:20]},
                            headers=auth_header(user))

    assert second.status_code == 422
    details = second.json()["details"]
    assert details["limit"] == 10
    assert len(details["already_held"]) == 10


async def test_booking_enforces_the_seat_limit_itself(
        api, token, auth_header, showtime_id, free_seats):
    """The booking endpoint does not assume the seats came through locking."""
    user = await token("greedy")

    # Held legitimately, one seat at a time, up to the limit.
    for seat in free_seats[:10]:
        await api.post(f"/showtimes/{showtime_id}/seats/lock",
                       json={"seats": [seat]}, headers=auth_header(user))

    ok = await api.post("/bookings",
                        json={"showtime_id": showtime_id,
                              "seats": free_seats[:10]},
                        headers=auth_header(user))
    assert ok.status_code == 201

    too_many = await api.post("/bookings",
                              json={"showtime_id": showtime_id,
                                    "seats": free_seats[:11]},
                              headers=auth_header(user))
    assert too_many.status_code == 422
    assert too_many.json()["details"]["limit"] == 10


async def test_relocking_held_seats_does_not_count_twice(
        api, token, auth_header, showtime_id, free_seats):
    """Re-sending the same selection must not trip the limit."""
    user = await token("user-1")
    seats = free_seats[:10]

    first = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                           json={"seats": seats}, headers=auth_header(user))
    repeat = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                            json={"seats": seats}, headers=auth_header(user))

    assert first.status_code == 201
    assert repeat.status_code == 201, "a retry was counted as new seats"


async def test_bookings_require_a_token(api, showtime_id):
    response = await api.post("/bookings",
                              json={"showtime_id": showtime_id,
                                    "seats": ["A2"]})
    assert response.status_code == 401


async def test_listing_returns_only_your_own_bookings(
        api, token, auth_header, showtime_id, free_seats):
    seats = free_seats[:1]
    user1, user2 = await asyncio.gather(token("user-1"), token("user-2"))
    await _hold(api, auth_header, showtime_id, user1, seats)
    await api.post("/bookings",
                   json={"showtime_id": showtime_id, "seats": seats},
                   headers=auth_header(user1))

    mine = await api.get("/bookings", headers=auth_header(user1))
    theirs = await api.get("/bookings", headers=auth_header(user2))

    assert len(mine.json()["data"]) == 1
    assert theirs.json()["data"] == []
