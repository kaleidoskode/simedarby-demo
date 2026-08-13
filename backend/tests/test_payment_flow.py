"""Payment, permanent reservation and ticket issue.

The important assertions here are about money and seats not being lost:
retrying must not charge twice, a declined card must leave nothing reserved,
and a confirmed seat must be impossible to sell again.
"""

import asyncio
import uuid

VALID_CARD = {"number": "4242 4242 4242 4242", "expiry": "12/29", "cvv": "123"}
DECLINED_CARD = {"number": "4000 0000 0000 0002", "expiry": "12/29",
                 "cvv": "123"}
CARD_PAYMENT = {"method": "debit_card", "card": VALID_CARD}


async def _booking(api, token, auth_header, showtime_id, seats, name="buyer"):
    """Hold seats and open a draft booking, returning (token, booking)."""
    user = await token(name)
    lock = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                          json={"seats": seats}, headers=auth_header(user))
    assert lock.status_code == 201, lock.text

    created = await api.post("/bookings",
                             json={"showtime_id": showtime_id, "seats": seats},
                             headers=auth_header(user))
    assert created.status_code == 201, created.text
    return user, created.json()["data"]


async def test_payment_methods_match_the_design(api):
    """The three options on the Payment screen."""
    response = await api.get("/payment-methods")
    assert response.status_code == 200

    methods = response.json()["data"]
    assert [m["id"] for m in methods] == [
        "debit_card", "bank_transfer", "crypto_wallet"]
    assert [m["requires_card"] for m in methods] == [True, False, False]


async def test_paying_confirms_the_booking(
        api, token, auth_header, showtime_id, free_seats):
    """The happy path: draft becomes confirmed and the card is not stored."""
    seats = free_seats[:2]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)

    response = await api.post(f"/bookings/{booking['id']}/pay",
                              json=CARD_PAYMENT, headers=auth_header(user))

    assert response.status_code == 200, response.text
    paid = response.json()["data"]

    assert paid["status"] == "confirmed"
    assert paid["confirmed_at"] is not None
    assert paid["expires_at"] is None
    assert paid["payment"]["status"] == "succeeded"
    assert paid["payment"]["method"] == "debit_card"
    assert paid["payment"]["reference"].startswith("PAY-")
    # Only the last four digits survive the request.
    assert paid["payment"]["card_last4"] == "4242"
    assert "number" not in paid["payment"]
    assert "cvv" not in paid["payment"]


async def test_paid_seats_show_as_booked_to_everyone(
        api, token, auth_header, showtime_id, free_seats):
    """After payment the seats are sold, not merely held."""
    seats = free_seats[:2]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)
    await api.post(f"/bookings/{booking['id']}/pay", json=CARD_PAYMENT,
                   headers=auth_header(user))

    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    states = {s["seat"]: s["status"] for row in plan.json()["data"]["rows"]
              for s in row["seats"] if s["seat"] in seats}

    assert states == {seat: "booked" for seat in seats}


async def test_a_sold_seat_cannot_be_locked_again(
        api, token, auth_header, showtime_id, free_seats):
    """The reservation outlives the lock, so nobody can take the seat."""
    seat = free_seats[0]
    user, booking = await _booking(api, token, auth_header, showtime_id, [seat])
    await api.post(f"/bookings/{booking['id']}/pay", json=CARD_PAYMENT,
                   headers=auth_header(user))

    other = await token("someone-else")
    response = await api.post(f"/showtimes/{showtime_id}/seats/lock",
                              json={"seats": [seat]},
                              headers=auth_header(other))

    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "booked"


async def test_retrying_with_the_same_key_does_not_charge_twice(
        api, token, auth_header, showtime_id, free_seats):
    """A lost response on a flaky network must not cost the user twice."""
    seats = free_seats[:2]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)
    headers = {**auth_header(user), "Idempotency-Key": str(uuid.uuid4())}

    first = await api.post(f"/bookings/{booking['id']}/pay",
                           json=CARD_PAYMENT, headers=headers)
    second = await api.post(f"/bookings/{booking['id']}/pay",
                            json=CARD_PAYMENT, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200, "the retry was refused"

    # Same transaction, not a second one.
    assert (second.json()["data"]["payment"]["reference"]
            == first.json()["data"]["payment"]["reference"])
    assert (second.json()["data"]["confirmed_at"]
            == first.json()["data"]["confirmed_at"])


async def test_paying_twice_without_a_key_is_refused(
        api, token, auth_header, showtime_id, free_seats):
    """Without an idempotency key a second payment is a conflict, not a sale."""
    seats = free_seats[:1]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)

    first = await api.post(f"/bookings/{booking['id']}/pay",
                           json=CARD_PAYMENT, headers=auth_header(user))
    second = await api.post(f"/bookings/{booking['id']}/pay",
                            json=CARD_PAYMENT, headers=auth_header(user))

    assert first.status_code == 200
    assert second.status_code == 409


async def test_simultaneous_payments_charge_only_once(
        api, token, auth_header, showtime_id, free_seats):
    """Two identical requests in flight together must produce one sale."""
    seats = free_seats[:2]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)
    headers = {**auth_header(user), "Idempotency-Key": str(uuid.uuid4())}

    responses = await asyncio.gather(*[
        api.post(f"/bookings/{booking['id']}/pay", json=CARD_PAYMENT,
                 headers=headers)
        for _ in range(5)
    ])

    codes = [r.status_code for r in responses]
    assert codes.count(200) >= 1, codes

    references = {r.json()["data"]["payment"]["reference"]
                  for r in responses if r.status_code == 200}
    assert len(references) == 1, f"charged more than once: {references}"

    # Exactly one reservation per seat, never a duplicate.
    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    booked = [s["seat"] for row in plan.json()["data"]["rows"]
              for s in row["seats"] if s["status"] == "booked"]
    assert sorted(set(seats) & set(booked)) == sorted(seats)


async def test_a_declined_card_reserves_nothing(
        api, token, auth_header, showtime_id, free_seats):
    """A refused payment must leave the seats unsold and retryable."""
    seats = free_seats[:2]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)

    declined = await api.post(f"/bookings/{booking['id']}/pay",
                              json={"method": "debit_card",
                                    "card": DECLINED_CARD},
                              headers=auth_header(user))

    assert declined.status_code == 402
    assert declined.json()["details"]["reason"] == "card_declined"

    # Nothing was reserved, so the seats are still only held.
    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    states = {s["seat"]: s["status"] for row in plan.json()["data"]["rows"]
              for s in row["seats"] if s["seat"] in seats}
    assert states == {seat: "locked" for seat in seats}

    # And the booking can be paid for with a different card.
    retry = await api.post(f"/bookings/{booking['id']}/pay",
                           json=CARD_PAYMENT, headers=auth_header(user))
    assert retry.status_code == 200
    assert retry.json()["data"]["status"] == "confirmed"


async def test_paying_without_holding_the_seats_is_refused(
        api, token, auth_header, showtime_id, free_seats, redis):
    """A hold that lapsed on the payment screen fails before money moves."""
    seats = free_seats[:1]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)

    # Simulate the user taking too long.
    await redis.delete(f"lock:{showtime_id}:{seats[0]}")

    response = await api.post(f"/bookings/{booking['id']}/pay",
                              json=CARD_PAYMENT, headers=auth_header(user))

    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "hold_expired"


async def test_card_details_are_validated(
        api, token, auth_header, showtime_id, free_seats):
    """A mistyped number is caught by its check digit, before anything else."""
    seats = free_seats[:1]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)

    for card in (
        {"number": "4242 4242 4242 4243", "expiry": "12/29", "cvv": "123"},
        {"number": "4242", "expiry": "12/29", "cvv": "123"},
        {"number": "4242 4242 4242 4242", "expiry": "01/20", "cvv": "123"},
        {"number": "4242 4242 4242 4242", "expiry": "13/29", "cvv": "123"},
    ):
        response = await api.post(f"/bookings/{booking['id']}/pay",
                                  json={"method": "debit_card", "card": card},
                                  headers=auth_header(user))
        assert response.status_code == 422, f"accepted bad card: {card}"


async def test_card_is_required_for_a_card_payment(
        api, token, auth_header, showtime_id, free_seats):
    seats = free_seats[:1]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)

    response = await api.post(f"/bookings/{booking['id']}/pay",
                              json={"method": "debit_card"},
                              headers=auth_header(user))
    assert response.status_code == 422


async def test_bank_transfer_needs_no_card(
        api, token, auth_header, showtime_id, free_seats):
    """The other two methods skip the card form entirely."""
    seats = free_seats[:1]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)

    response = await api.post(f"/bookings/{booking['id']}/pay",
                              json={"method": "bank_transfer"},
                              headers=auth_header(user))

    assert response.status_code == 200
    paid = response.json()["data"]
    assert paid["status"] == "confirmed"
    assert paid["payment"]["method"] == "bank_transfer"
    assert paid["payment"]["card_last4"] is None


async def test_ticket_is_issued_after_payment(
        api, token, auth_header, showtime_id, free_seats):
    """The View ticket screen, matching the wireframe's summary."""
    seats = free_seats[:2]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)
    await api.put(f"/bookings/{booking['id']}/fnb",
                  json={"items": [{"fnb_id": "fnb_fresh_xl_combo",
                                   "quantity": 1}]},
                  headers=auth_header(user))
    await api.post(f"/bookings/{booking['id']}/pay", json=CARD_PAYMENT,
                   headers=auth_header(user))

    response = await api.get(f"/bookings/{booking['id']}/ticket",
                             headers=auth_header(user))

    assert response.status_code == 200
    ticket = response.json()["data"]

    assert ticket["reference"] == booking["reference"]
    assert ticket["movie_title"] == "Venom: Let There Be Carnage"
    assert ticket["cinema_name"] == "GSC Mid Valley Megamall"
    assert ticket["seats"] == seats
    assert ticket["start_display"] == "5:40PM"
    assert ticket["end_display"] == "7:20PM"
    assert ticket["total_paid"]["display"] == "RM104.50"
    # The QR carries the reference only, so scanning is a lookup.
    assert ticket["qr_payload"] == booking["reference"]


async def test_no_ticket_before_payment(
        api, token, auth_header, showtime_id, free_seats):
    seats = free_seats[:1]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)

    response = await api.get(f"/bookings/{booking['id']}/ticket",
                             headers=auth_header(user))

    assert response.status_code == 409
    assert response.json()["details"]["status"] == "draft"


async def test_a_confirmed_booking_cannot_be_cancelled(
        api, token, auth_header, showtime_id, free_seats):
    """Once paid, the seats are sold and the draft flow no longer applies."""
    seats = free_seats[:1]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)
    await api.post(f"/bookings/{booking['id']}/pay", json=CARD_PAYMENT,
                   headers=auth_header(user))

    response = await api.delete(f"/bookings/{booking['id']}",
                                headers=auth_header(user))
    assert response.status_code == 409


async def test_confirmed_seats_are_broadcast_as_booked(
        api, token, auth_header, showtime_id, free_seats):
    """Watchers see the seats go from locked to sold."""
    seats = free_seats[:1]
    user, booking = await _booking(api, token, auth_header, showtime_id, seats)

    plan = await api.get(f"/showtimes/{showtime_id}/seats")
    version = plan.json()["data"]["version"]

    await api.post(f"/bookings/{booking['id']}/pay", json=CARD_PAYMENT,
                   headers=auth_header(user))

    changes = await api.get(f"/showtimes/{showtime_id}/seats/changes",
                            params={"since": version})
    published = changes.json()["data"]["changes"]
    assert {"seat": seats[0], "status": "booked"} in [
        {"seat": c["seat"], "status": c["status"]} for c in published]


async def test_payment_requires_a_token(api, showtime_id, free_seats):
    response = await api.post("/bookings/bkg_whatever/pay", json=CARD_PAYMENT)
    assert response.status_code == 401
