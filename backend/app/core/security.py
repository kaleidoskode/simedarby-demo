"""Stateless caller identity.

Every request carries a self-describing JWT and the server keeps no session.
That is what makes the API horizontally scalable: any worker can serve any
request, because everything it needs to authorise the call is in the token,
and everything it needs to act on is in Redis or MongoDB.

HS256 is used rather than RS256 because this service both mints and verifies
the token; there is no third party that needs to verify without being able to
sign, which is the case asymmetric keys exist for.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.middleware.exception import CustomErrorException
from app.schemas.auth_schema import CurrentUser

# auto_error is off so a missing header produces our own 401 envelope rather
# than FastAPI's default shape, keeping every error response consistent.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the access_token returned by POST /api/v1/auth/token",
)


def new_user_id() -> str:
    """Generate an opaque identifier for a guest."""
    return f"usr_{uuid.uuid4().hex[:12]}"


def create_access_token(user_id: str, name: str) -> Tuple[str, int]:
    """Mint a signed token. Returns the token and its lifetime in seconds."""
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=settings.jwt_ttl_seconds)

    payload = {
        "sub": user_id,
        "name": name,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "exp": expires_at,
    }

    token = jwt.encode(payload, settings.jwt_secret,
                       algorithm=settings.jwt_algorithm)
    return token, settings.jwt_ttl_seconds


def decode_token(token: str) -> dict:
    """Verify a token and return its claims, or raise a 401."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            # Pinning the algorithm matters: accepting whatever the token
            # declares is how "alg": "none" and HS/RS confusion attacks work.
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise CustomErrorException(
            "Token has expired, request a new one", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise CustomErrorException(
            f"Invalid token: {exc}", status_code=401) from exc


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> CurrentUser:
    """Resolve the caller from the Authorization header.

    Used on the endpoints that own or mutate something: locking a seat,
    creating a booking, paying. The catalogue is public, matching the design,
    where the app opens onto the home screen without a login.
    """
    if credentials is None or not credentials.credentials:
        raise CustomErrorException(
            "Missing bearer token. Call POST /api/v1/auth/token first.",
            status_code=401)

    claims = decode_token(credentials.credentials)
    return CurrentUser(id=claims["sub"], name=claims.get("name", "Guest"))
