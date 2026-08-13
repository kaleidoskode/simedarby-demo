"""Issuing guest access tokens."""

import logging

from app.core.security import create_access_token, new_user_id
from app.schemas.auth_schema import (
    CurrentUser,
    GuestTokenRequest,
    TokenResponse,
)

logger = logging.getLogger(__name__)


class AuthServices:
    """Mints the tokens that identify a caller.

    Deliberately holds no state and touches no datastore. A guest identity is
    created inside the token itself, so nothing has to be written down and no
    session has to be looked up on subsequent requests.
    """

    async def issue_guest_token(
            self, payload: GuestTokenRequest) -> TokenResponse:
        """Create a new guest identity and return a signed token for it."""
        user = CurrentUser(id=new_user_id(), name=payload.name)
        token, expires_in = create_access_token(user.id, user.name)

        logger.info("Issued guest token for %s", user.id)

        return TokenResponse(
            access_token=token,
            expires_in=expires_in,
            user=user,
        )
