"""Authentication endpoints."""

import logging

from fastapi import APIRouter, Body, Depends

from app.core.construct_services import auth
from app.core.security import get_current_user
from app.helpers.generic_response import GenericResponse
from app.schemas.auth_schema import (
    CurrentUser,
    GuestTokenRequest,
    TokenResponse,
)
from app.services import auth_services

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/token", response_model=GenericResponse[TokenResponse],
             summary="Issue a guest access token")
async def issue_token(
    *,
    service: auth_services.AuthServices = Depends(auth),
    payload: GuestTokenRequest = Body(default=GuestTokenRequest()),
):
    """Start a session without an account.

    The design opens straight onto the home screen, so no sign-up exists. This
    returns a signed token that identifies the caller for the rest of the flow;
    it is what a seat lock is owned by, and what stops one user releasing
    another user's seat.

    Nothing is stored server side, so the token is the whole session.
    """
    data = await service.issue_guest_token(payload)
    return GenericResponse(message="Token issued", data=data)


@router.get("/me", response_model=GenericResponse[CurrentUser],
            summary="Resolve the caller from the bearer token")
async def read_me(user: CurrentUser = Depends(get_current_user)):
    """Echo back the identity carried in the token.

    Useful for confirming a token is valid, and it demonstrates the point of a
    stateless design: the answer is reconstructed from the request itself, with
    no session lookup.
    """
    return GenericResponse(message="Token is valid", data=user)
