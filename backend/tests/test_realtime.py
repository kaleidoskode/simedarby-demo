"""Proof that seat changes reach other users in real time.

The scenario in 1.0: User 1 is looking at the seating plan when User 2 takes a
seat, and User 1's plan must show it immediately.

Both transports are exercised against the same events, because the point of
putting them on one Redis stream is that they cannot disagree.
"""

import asyncio
import json

import pytest
import websockets

from tests.conftest import BASE_URL

WS_BASE = BASE_URL.replace("http://", "ws://").replace("https://", "wss://")
RECEIVE_TIMEOUT = 5.0


async def _recv(socket, expected_type: str, timeout: float = RECEIVE_TIMEOUT):
    """Wait for the next message of a given type."""
    async with asyncio.timeout(timeout):
        while True:
            message = json.loads(await socket.recv())
            if message["type"] == expected_type:
                return message


async def test_socket_opens_with_a_snapshot_of_the_plan(showtime_id):
    """A client gets the full plan on connect, with no extra REST call."""
    async with websockets.connect(
            f"{WS_BASE}/api/v1/ws/showtimes/{showtime_id}") as socket:
        snapshot = await _recv(socket, "snapshot")

    plan = snapshot["plan"]
    assert plan["showtime_id"] == showtime_id
    assert plan["summary"]["total"] == 60
    assert snapshot["version"] == plan["version"]
    assert len(plan["rows"]) == 8


async def test_a_lock_by_someone_else_arrives_over_the_socket(
        api, token, auth_header, showtime_id, free_seats):
    """User 1 is watching; User 2 takes a seat; User 1 is told."""
    seat = free_seats[0]
    user2 = await token("user-2")

    async with websockets.connect(
            f"{WS_BASE}/api/v1/ws/showtimes/{showtime_id}") as socket:
        await _recv(socket, "snapshot")

        response = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                                  json={"seats": [seat]},
                                  headers=auth_header(user2))
        assert response.status_code == 201

        event = await _recv(socket, "seat_change")

    change = event["changes"][0]
    assert change["seat"] == seat
    assert change["status"] == "locked"
    # The watcher is anonymous, so this is somebody else's hold.
    assert change["held_by_me"] is False


async def test_a_release_arrives_over_the_socket(
        api, token, auth_header, showtime_id, free_seats):
    """Freeing a seat is broadcast too, so the plan can repaint it."""
    seat = free_seats[0]
    user = await token("user-1")

    await api.post(f"/showtimes/{showtime_id}/seats/lock",
                   json={"seats": [seat]}, headers=auth_header(user))

    async with websockets.connect(
            f"{WS_BASE}/api/v1/ws/showtimes/{showtime_id}") as socket:
        await _recv(socket, "snapshot")

        await api.request("DELETE", f"/showtimes/{showtime_id}/seats/lock",
                          json={"seats": [seat]}, headers=auth_header(user))

        event = await _recv(socket, "seat_change")

    assert event["changes"][0] == {
        "seat": seat, "status": "available", "held_by_me": False,
        "at": event["changes"][0]["at"],
    }


async def test_the_holder_sees_their_own_change_as_theirs(
        api, token, auth_header, showtime_id, free_seats):
    """held_by_me is resolved per recipient, not per event."""
    seat = free_seats[0]
    user = await token("user-1")

    # Identify the socket as the same user that will take the seat.
    async with websockets.connect(
            f"{WS_BASE}/api/v1/ws/showtimes/{showtime_id}?token={user}"
    ) as socket:
        await _recv(socket, "snapshot")

        await api.post(f"/showtimes/{showtime_id}/seats/lock",
                       json={"seats": [seat]}, headers=auth_header(user))

        event = await _recv(socket, "seat_change")

    assert event["changes"][0]["held_by_me"] is True


async def test_two_watchers_both_receive_the_change(
        api, token, auth_header, showtime_id, free_seats):
    """Fan-out reaches every subscriber, not just the first."""
    seat = free_seats[0]
    user = await token("locker")

    url = f"{WS_BASE}/api/v1/ws/showtimes/{showtime_id}"
    async with websockets.connect(url) as first, \
            websockets.connect(url) as second:
        await asyncio.gather(_recv(first, "snapshot"),
                             _recv(second, "snapshot"))

        await api.post(f"/showtimes/{showtime_id}/seats/lock",
                       json={"seats": [seat]}, headers=auth_header(user))

        events = await asyncio.gather(_recv(first, "seat_change"),
                                      _recv(second, "seat_change"))

    for event in events:
        assert event["changes"][0]["seat"] == seat
        assert event["changes"][0]["status"] == "locked"


async def test_polling_returns_the_same_change_as_the_socket(
        api, token, auth_header, showtime_id, free_seats):
    """The two transports must never disagree; they read one log."""
    seat = free_seats[0]
    user = await token("user-1")

    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    version = plan.json()["data"]["version"]

    async with websockets.connect(
            f"{WS_BASE}/api/v1/ws/showtimes/{showtime_id}") as socket:
        await _recv(socket, "snapshot")

        await api.post(f"/showtimes/{showtime_id}/seats/lock",
                       json={"seats": [seat]}, headers=auth_header(user))

        pushed = await _recv(socket, "seat_change")

    polled = await api.get(f"/showtimes/{showtime_id}/seats/changes",
                           params={"since": version})
    assert polled.status_code == 200
    body = polled.json()["data"]

    assert len(body["changes"]) == 1
    assert body["changes"][0]["seat"] == pushed["changes"][0]["seat"]
    assert body["changes"][0]["status"] == pushed["changes"][0]["status"]
    assert body["version"] == pushed["version"]


async def test_polling_is_exclusive_of_the_version_supplied(
        api, token, auth_header, showtime_id, free_seats):
    """Polling twice must not replay a change the client already applied."""
    seat = free_seats[0]
    user = await token("user-1")

    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    version = plan.json()["data"]["version"]

    await api.post(f"/showtimes/{showtime_id}/seats/lock",
                   json={"seats": [seat]}, headers=auth_header(user))

    first = await api.get(f"/showtimes/{showtime_id}/seats/changes",
                          params={"since": version})
    first_body = first.json()["data"]
    assert len(first_body["changes"]) == 1

    # Polling again from the returned version yields nothing new, and the
    # version is echoed so the client keeps its place.
    second = await api.get(f"/showtimes/{showtime_id}/seats/changes",
                           params={"since": first_body["version"]})
    second_body = second.json()["data"]
    assert second_body["changes"] == []
    assert second_body["version"] == first_body["version"]


async def test_polling_catches_up_everything_missed(
        api, token, auth_header, showtime_id, free_seats):
    """A client offline for several changes gets them all on reconnect.

    This is what a stream buys over pub/sub, which cannot replay at all.
    """
    seats = free_seats[:3]
    user = await token("user-1")

    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    version = plan.json()["data"]["version"]

    for seat in seats:
        await api.post(f"/showtimes/{showtime_id}/seats/lock",
                       json={"seats": [seat]}, headers=auth_header(user))

    response = await api.get(f"/showtimes/{showtime_id}/seats/changes",
                             params={"since": version})
    changes = response.json()["data"]["changes"]

    assert [c["seat"] for c in changes] == seats
    assert all(c["status"] == "locked" for c in changes)


async def test_a_bad_version_is_rejected(api, showtime_id):
    """A malformed version is a client error, not a server crash."""
    response = await api.get(f"/showtimes/{showtime_id}/seats/changes",
                             params={"since": "not-a-version"})
    assert response.status_code == 422


async def test_socket_rejects_an_invalid_token(showtime_id):
    """A bad token is refused rather than silently downgraded to anonymous."""
    with pytest.raises(websockets.exceptions.WebSocketException):
        async with websockets.connect(
                f"{WS_BASE}/api/v1/ws/showtimes/{showtime_id}?token=rubbish"
        ) as socket:
            await _recv(socket, "snapshot", timeout=2.0)


async def test_socket_rejects_an_unknown_showtime():
    """Connecting to a screening that does not exist is closed, not hung."""
    with pytest.raises(websockets.exceptions.WebSocketException):
        async with websockets.connect(
                f"{WS_BASE}/api/v1/ws/showtimes/sho_does_not_exist"
        ) as socket:
            await _recv(socket, "snapshot", timeout=2.0)
