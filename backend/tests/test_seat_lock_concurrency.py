"""Proof that seat locking is first come first serve.

The assignment's core claim is that when two users go for the same seat, one
wins and the rest are refused. These tests assert that against real Redis,
through the HTTP surface, across gunicorn worker processes.
"""

import asyncio

import pytest

CONTENDERS = 50


async def test_only_one_of_many_simultaneous_users_wins_a_seat(
        api, token, auth_header, showtime_id, free_seats):
    """50 users go for one seat at the same instant. Exactly one gets it.

    This is the requirement in 1.0: as User 2 starts booking seat A3, every
    other user is locked out of it.
    """
    seat = free_seats[0]
    tokens = await asyncio.gather(
        *[token(f"racer-{i}") for i in range(CONTENDERS)])

    # Fire every request without awaiting in between, so they are genuinely in
    # flight together rather than serialised by the test itself.
    responses = await asyncio.gather(*[
        api.post(f"/showtimes/{showtime_id}/seats/lock",
                 json={"seats": [seat]}, headers=auth_header(t))
        for t in tokens
    ])

    codes = [r.status_code for r in responses]
    winners = [r for r in responses if r.status_code == 201]
    losers = [r for r in responses if r.status_code == 409]

    assert len(winners) == 1, (
        f"expected exactly one winner, got {codes.count(201)}. "
        f"status codes: {sorted(set(codes))}")
    assert len(losers) == CONTENDERS - 1
    assert len(winners) + len(losers) == CONTENDERS, (
        f"unexpected status codes present: {sorted(set(codes))}")

    # The refusals must say which seat was contested, so the client can repaint
    # exactly that seat instead of reloading the plan.
    for response in losers:
        assert response.json()["details"]["conflicts"] == [seat]


async def test_a_locked_seat_shows_as_locked_to_everyone_else(
        api, token, auth_header, showtime_id, free_seats):
    """User 1 sees User 2's hold appear on their own seating plan."""
    seat = free_seats[0]
    user1, user2 = await asyncio.gather(token("user-1"), token("user-2"))

    before = await api.get(f"/showtimes/{showtime_id}/seats",
                           headers=auth_header(user1))
    assert _state(before.json()["data"], seat)["status"] == "available"

    locked = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                            json={"seats": [seat]},
                            headers=auth_header(user2))
    assert locked.status_code == 201

    # User 1 sees it as locked, and crucially not as their own selection.
    after = await api.get(f"/showtimes/{showtime_id}/seats",
                          headers=auth_header(user1))
    seen_by_user1 = _state(after.json()["data"], seat)
    assert seen_by_user1["status"] == "locked"
    assert seen_by_user1["held_by_me"] is False

    # The holder sees the same seat as their own, which is what the design
    # renders as Selected rather than unavailable.
    owner_view = await api.get(f"/showtimes/{showtime_id}/seats",
                               headers=auth_header(user2))
    assert _state(owner_view.json()["data"], seat)["held_by_me"] is True


async def test_multi_seat_lock_is_all_or_nothing(
        api, token, auth_header, showtime_id, free_seats):
    """A partly taken selection holds nothing at all."""
    taken, wanted = free_seats[0], free_seats[1]
    user1, user2 = await asyncio.gather(token("user-1"), token("user-2"))

    first = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                           json={"seats": [taken]},
                           headers=auth_header(user1))
    assert first.status_code == 201

    # User 2 asks for one free seat and one already held.
    second = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                            json={"seats": [wanted, taken]},
                            headers=auth_header(user2))
    assert second.status_code == 409
    assert second.json()["details"]["conflicts"] == [taken]

    # The free seat must not have been held as a side effect of the failure.
    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    assert _state(plan.json()["data"], wanted)["status"] == "available"


async def test_only_the_holder_can_release_a_seat(
        api, token, auth_header, showtime_id, free_seats):
    """User 2 cannot free a seat that User 1 is holding."""
    seat = free_seats[0]
    user1, user2 = await asyncio.gather(token("user-1"), token("user-2"))

    await api.post(f"/showtimes/{showtime_id}/seats/lock",
                   json={"seats": [seat]}, headers=auth_header(user1))

    stolen = await api.request(
        "DELETE", f"/showtimes/{showtime_id}/seats/lock",
        json={"seats": [seat]}, headers=auth_header(user2))

    assert stolen.status_code == 200
    body = stolen.json()["data"]
    assert body["released"] == [], "another user's hold was released"
    assert body["ignored"] == [seat]

    # Still held by the original user.
    plan = await api.get(f"/showtimes/{showtime_id}/seats",
                         headers=auth_header(user1))
    assert _state(plan.json()["data"], seat)["held_by_me"] is True


async def test_releasing_frees_the_seat_for_the_next_user(
        api, token, auth_header, showtime_id, free_seats):
    """After a release the seat is immediately winnable by someone else."""
    seat = free_seats[0]
    user1, user2 = await asyncio.gather(token("user-1"), token("user-2"))

    await api.post(f"/showtimes/{showtime_id}/seats/lock",
                   json={"seats": [seat]}, headers=auth_header(user1))

    blocked = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                             json={"seats": [seat]},
                             headers=auth_header(user2))
    assert blocked.status_code == 409

    await api.request("DELETE", f"/showtimes/{showtime_id}/seats/lock",
                      json={"seats": [seat]}, headers=auth_header(user1))

    now_free = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                              json={"seats": [seat]},
                              headers=auth_header(user2))
    assert now_free.status_code == 201


async def test_a_hold_expires_by_itself(
        api, token, auth_header, showtime_id, free_seats, redis):
    """The TTL frees an abandoned seat with no sweeper job involved.

    Waiting out the real TTL would make the suite slow, so the key's expiry is
    shortened directly. What is being asserted is that expiry alone releases
    the seat, not the exact duration.
    """
    seat = free_seats[0]
    user1, user2 = await asyncio.gather(token("user-1"), token("user-2"))

    await api.post(f"/showtimes/{showtime_id}/seats/lock",
                   json={"seats": [seat]}, headers=auth_header(user1))

    key = f"lock:{showtime_id}:{seat}"
    assert await redis.ttl(key) > 0, "lock was created without a TTL"

    await redis.pexpire(key, 150)
    await asyncio.sleep(0.4)

    assert await redis.exists(key) == 0

    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    assert _state(plan.json()["data"], seat)["status"] == "available"

    taken_by_next = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                                   json={"seats": [seat]},
                                   headers=auth_header(user2))
    assert taken_by_next.status_code == 201


async def test_heartbeat_extends_only_seats_still_held(
        api, token, auth_header, showtime_id, free_seats, redis):
    """A heartbeat refreshes a live hold and does not revive a lapsed one."""
    kept, lapsed = free_seats[0], free_seats[1]
    user = await token("user-1")

    await api.post(f"/showtimes/{showtime_id}/seats/lock",
                   json={"seats": [kept, lapsed]}, headers=auth_header(user))

    # Let one of the two expire.
    await redis.delete(f"lock:{showtime_id}:{lapsed}")
    await redis.pexpire(f"lock:{showtime_id}:{kept}", 500)

    response = await api.post(
        f"/showtimes/{showtime_id}/seats/lock/heartbeat",
        json={"seats": [kept, lapsed]}, headers=auth_header(user))

    assert response.status_code == 200
    assert response.json()["data"]["seats"] == [kept]

    # The surviving hold got its full TTL back.
    assert await redis.ttl(f"lock:{showtime_id}:{kept}") > 60
    assert await redis.exists(f"lock:{showtime_id}:{lapsed}") == 0


async def test_relocking_your_own_seat_is_idempotent(
        api, token, auth_header, showtime_id, free_seats):
    """A retried request must not refuse the caller their own seat."""
    seat = free_seats[0]
    user = await token("user-1")

    first = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                           json={"seats": [seat]}, headers=auth_header(user))
    second = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                            json={"seats": [seat]}, headers=auth_header(user))

    assert first.status_code == 201
    assert second.status_code == 201, "a client retry was rejected"


async def test_a_sold_seat_cannot_be_locked(
        api, token, auth_header, showtime_id):
    """Seats already booked are refused before Redis is consulted."""
    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    booked = [seat["seat"] for row in plan.json()["data"]["rows"]
              for seat in row["seats"] if seat["status"] == "booked"]
    if not booked:
        pytest.skip("this screening has no pre-sold seats")

    user = await token("user-1")
    response = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                              json={"seats": [booked[0]]},
                              headers=auth_header(user))

    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "booked"


async def test_locking_requires_a_token(api, showtime_id, free_seats):
    """A hold must have an owner, so anonymous locking is refused."""
    response = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                              json={"seats": [free_seats[0]]})
    assert response.status_code == 401


def _state(plan: dict, seat: str) -> dict:
    """Pull one seat's state out of a seating plan response."""
    for row in plan["rows"]:
        for state in row["seats"]:
            if state["seat"] == seat:
                return state
    raise AssertionError(f"seat {seat} not present in the plan")
