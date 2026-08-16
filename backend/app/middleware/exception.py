import logging
import re
import traceback
from typing import Any, Iterable, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


logger = logging.getLogger(__name__)

# Pydantic prefixes a custom ValueError with "Value error, ". The text after it
# is the sentence written for a human, which is the part worth returning.
_VALUE_ERROR_PREFIX = re.compile(r"^Value error,\s*")


def _error_body(error: str, message: str, traceback_text: str,
                details: Optional[dict] = None) -> dict:
    """Build an error payload, attaching the traceback only off production.

    A stack trace names internal file paths and module structure, so it is
    logged everywhere but returned to the caller only outside production.
    """
    body = {"success": False, "error": error, "message": message}
    if details:
        body["details"] = details
    if settings.expose_error_debug and traceback_text:
        body["debug"] = traceback_text
    return body


def _field_path(location: Iterable[Any]) -> str:
    """Name the offending field the way the caller wrote it.

    Pydantic reports `("body", "card", "expiry")`. The leading marker says
    where in the request it was found, which the caller already knows, so what
    is left is the path inside their own payload: `card.expiry`.
    """
    parts = [str(part) for part in location
             if part not in ("body", "query", "path", "header", "cookie")]
    return ".".join(parts)


async def http_exception_handler(
        request: Request, exc: HTTPException) -> JSONResponse:
    """Return the envelope for the errors the framework raises on our behalf.

    A mistyped URL and a wrong method never reach a route, so nothing in this
    codebase gets to answer them — Starlette raises `HTTPException` during
    routing and FastAPI's default handler renders `{"detail": ...}`. That is a
    second error shape for a client to parse, arriving precisely when it is
    least expected, and it is what makes a typo look like an outage.

    Registered against **Starlette's** `HTTPException`, not FastAPI's. FastAPI's
    is a subclass, and a handler registered for a subclass never sees the parent
    the router actually raises — so binding to the subclass would silently keep
    the default for exactly the 404 and 405 this exists to fix.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body("HTTPException", str(exc.detail), ""),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
        request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a 422 in the same envelope as every other failure.

    FastAPI's default body is `{"detail": [...]}` — no `success`, no `message`.
    A client that reads `message` everywhere else therefore shows an
    unexplained failure, and the most useful thing in the response is lost:
    "Expiry must be in MM/YY format" is precisely what the user needs to see.

    `details.fields` keeps the per-field breakdown, so a form can mark the
    individual input rather than only showing a sentence.
    """
    fields = [
        {
            "field": _field_path(error.get("loc", ())),
            "message": _VALUE_ERROR_PREFIX.sub("", error.get("msg", "")),
        }
        for error in exc.errors()
    ]

    if len(fields) == 1:
        message = fields[0]["message"]
    else:
        message = "; ".join(f"{f['field']}: {f['message']}" for f in fields)

    logger.info("Rejected %s %s: %s", request.method, request.url.path, message)

    return JSONResponse(
        status_code=422,
        content=_error_body("ValidationError", message, "", {"fields": fields}),
    )


# CustomErrorException class definition


class CustomErrorException(Exception):
    """An error with an HTTP status and optional machine readable detail.

    `details` carries structure the client needs to act on rather than just
    display. A seat lock conflict, for example, returns which seats were taken,
    so the app can repaint exactly those instead of reloading the whole plan.
    """

    def __init__(self, message: str, status_code: int = 500,
                 details: Optional[dict] = None):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class ExceptionHandler(BaseHTTPMiddleware):
    # Overriding the dispatch method from the BaseHTTPMiddleware. This method is called when a request is received.
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        # No `except HTTPException` here. FastAPI installs a handler for it
        # that runs *inside* this middleware, so one raised in a route is
        # already a response by the time it reaches here — the branch that used
        # to sit at this spot could never fire. `http_exception_handler` above
        # is where that case is answered now.
        except CustomErrorException as custom_exc:

            # Try to get the original exception's traceback
            original_tb = None
            if hasattr(custom_exc, '__cause__') and custom_exc.__cause__:
                original_tb = custom_exc.__cause__.__traceback__
            elif hasattr(custom_exc, '__context__') and custom_exc.__context__:
                original_tb = custom_exc.__context__.__traceback__

            # Use original traceback if available, otherwise use the current one
            if original_tb:
                tb = traceback.extract_tb(original_tb)
            else:
                tb = traceback.extract_tb(custom_exc.__traceback__)

            # Show more frames (last 5 instead of just 1)
            short_tb = tb[-5:] if len(tb) > 5 else tb
            formatted_tb = ''.join(traceback.format_list(short_tb))
            status_code = getattr(custom_exc, "status_code", 500)
            logger.error(
                "%s: %s\n%s",
                custom_exc.__class__.__name__,
                custom_exc.message,
                formatted_tb,
            )

            return JSONResponse(
                status_code=status_code,
                content=_error_body(
                    custom_exc.__class__.__name__,
                    custom_exc.message,
                    formatted_tb,
                    getattr(custom_exc, "details", None),
                ),
            )

        except Exception as e:

            # Extract traceback object
            tb = traceback.extract_tb(e.__traceback__)

            # Limit the number of frames to include in the response (e.g., last 5 frames)
            short_tb = tb[-1:]

            # Format the limited traceback
            formatted_tb = ''.join(traceback.format_list(short_tb))

            status_code = getattr(e, "status_code", 500)

            logger.error(
                "Unhandled %s: %s", e.__class__.__name__, e, exc_info=True)

            return JSONResponse(
                status_code=status_code,
                content=_error_body(
                    e.__class__.__name__, str(e), formatted_tb),
            )
