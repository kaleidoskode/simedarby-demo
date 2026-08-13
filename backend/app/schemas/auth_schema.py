"""Authentication models.

The booking flow needs an identity so a seat lock has an owner and only that
owner can release or pay for it. It does not need an account: the app opens
straight onto the home screen in the design, so a guest token is issued on
demand.
"""

from pydantic import BaseModel, Field


class GuestTokenRequest(BaseModel):
    """Body of POST /auth/token."""

    name: str = Field(default="Guest", min_length=1, max_length=60,
                      examples=["Raymond"])


class CurrentUser(BaseModel):
    """The caller, as reconstructed from the token on every request."""

    id: str = Field(..., examples=["usr_8f2a7c1e"])
    name: str = Field(..., examples=["Raymond"])


class TokenResponse(BaseModel):
    """A freshly minted access token."""

    access_token: str = Field(..., examples=["eyJhbGciOiJIUzI1NiIs..."])
    token_type: str = Field(default="bearer", examples=["bearer"])
    expires_in: int = Field(..., description="Lifetime in seconds",
                            examples=[3600])
    user: CurrentUser
