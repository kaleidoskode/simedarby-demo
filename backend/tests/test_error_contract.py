"""One error shape, whoever produced it.

Every success carries `{success, message, data}`, so every failure has to carry
the matching envelope — otherwise a client needs two parsers and picks the
wrong one exactly when something has already gone wrong.

The paths that are easy to miss are the ones the application never writes: a
mistyped URL and a wrong method are answered by the framework's routing, not by
any handler in this codebase, and they default to a different shape.
"""

ENVELOPE_KEYS = {"success", "error", "message"}


def _assert_envelope(response, expected_status: int):
    """A failure a client can parse the same way as every other failure."""
    assert response.status_code == expected_status, response.text

    body = response.json()
    missing = ENVELOPE_KEYS - set(body)
    assert not missing, f"missing {sorted(missing)} from {body}"

    assert body["success"] is False, body
    assert body["message"], f"empty message in {body}"
    # `detail` is the framework's own shape; its presence means something
    # bypassed the envelope.
    assert "detail" not in body, body


async def test_an_unknown_route_uses_the_error_envelope(api):
    """A mistyped URL is answered by the router, not by our code."""
    response = await api.get("/no-such-endpoint")
    _assert_envelope(response, 404)


async def test_a_wrong_method_uses_the_error_envelope(api):
    """405 comes from route matching, and is just as easy to hit by accident."""
    response = await api.request("DELETE", "/movies")
    _assert_envelope(response, 405)


async def test_an_unknown_resource_uses_the_error_envelope(api):
    """A well formed request for something that does not exist."""
    response = await api.get("/movies/mov_does_not_exist")
    _assert_envelope(response, 404)


async def test_a_missing_token_uses_the_error_envelope(api):
    """Authentication failures are read by the client to prompt a re-login."""
    response = await api.post("/bookings", json={})
    _assert_envelope(response, 401)


async def test_a_malformed_body_uses_the_error_envelope(api):
    """Validation is the case most likely to need its message shown verbatim."""
    response = await api.post("/auth/token", json={"name": 12345})
    _assert_envelope(response, 422)
