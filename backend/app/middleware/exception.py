import logging
import traceback
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


logger = logging.getLogger(__name__)


def _error_body(error: str, message: str, traceback_text: str,
                details: Optional[dict] = None) -> dict:
    """Build an error payload, attaching the traceback only off production.

    A stack trace names internal file paths and module structure, so it is
    logged everywhere but returned to the caller only outside production.
    """
    body = {"success": False, "error": error, "message": message}
    if details:
        body["details"] = details
    if settings.expose_error_debug:
        body["debug"] = traceback_text
    return body


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
        except HTTPException as http_exception:
            return JSONResponse(
                status_code=http_exception.status_code,
                content={'success': False, "error": "Client Error",
                         "message": str(http_exception.detail)},
            )

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
