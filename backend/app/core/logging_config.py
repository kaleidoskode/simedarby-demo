"""Application logging setup.

Without this the root logger sits at WARNING with no handlers, so every
`logger.info` in the codebase is discarded and `logger.error` escapes only
through Python's unformatted handler of last resort, with no timestamp, level
or module name. That matters most for the exception middleware, which logs the
stack trace it deliberately withholds from the client in production.
"""

import logging
import sys

from app.core.config import settings

# The process id is included because the app runs under several gunicorn
# workers. Which worker served a request matters when reasoning about the
# WebSocket fan-out, where one worker holds the socket and another may handle
# the lock that triggers the message.
_FORMAT = ("[%(asctime)s] %(levelname)s [pid %(process)d] "
           "[%(name)s:%(lineno)d] %(message)s")
_DATE_FORMAT = "%d/%b/%Y %H:%M:%S"

_configured = False


def configure_logging() -> None:
    """Attach a stdout handler to the root logger, honouring APP_LOGGING_LEVEL.

    Safe to call more than once: each worker process configures itself, and a
    repeat call in the same process is a no-op rather than a duplicated line.

    Only the root logger is touched. Uvicorn and gunicorn attach handlers to
    their own named loggers, so their access and error logs are unaffected.
    """
    global _configured
    if _configured:
        return

    level = logging.getLevelName(settings.logging_level.upper())
    if not isinstance(level, int):
        level = logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    _configured = True
