"""Which environment this process is, and where its settings come from.

Two files, two jobs:

    .env                 one line — ENVIRONMENT=local
    .env.<environment>   the settings for that environment

Switching target is a one word edit in `.env`, and the credentials for each
environment stay in separate files rather than side by side in one. That is why
there are no `_LOCAL` / `_DEV` / `_PROD` suffixes anywhere: the file *is* the
suffix, so `MONGO1_HOST` means the host for whichever environment is selected.

**Nothing loaded here overrides a variable already set in the real
environment.** That is deliberate, and it is what lets one mechanism serve two
very different ways of running the service:

* `docker compose up` injects the settings directly, and the `.env` files are
  not even present in the image. The real environment wins, which is correct —
  compose is always the local stack.
* `uv run -m app.main`, or a plain `docker run`, has no such injection, so the
  files are read from disk instead.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# app/core/environment.py -> app/core -> app -> the backend root.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

SWITCH_FILE = BACKEND_ROOT / ".env"

DEFAULT_ENVIRONMENT = "local"


def settings_file(name: str) -> Path:
    """Where the settings for an environment live."""
    return BACKEND_ROOT / f".env.{name}"


def _load() -> str:
    """Read the switch, then the settings file it names."""
    load_dotenv(SWITCH_FILE)

    name = os.getenv("ENVIRONMENT", DEFAULT_ENVIRONMENT).strip().lower()

    # A missing file is not fatal on its own: under docker compose the settings
    # arrive as real environment variables and no file is expected. It only
    # becomes a problem if a required value is then also absent, which
    # `describe_source` explains at the point that actually fails.
    load_dotenv(settings_file(name))

    return name


ENVIRONMENT: str = _load()

SETTINGS_FILE = settings_file(ENVIRONMENT)


def describe_source() -> str:
    """A hint for error messages, naming where a setting was looked for.

    A missing host is nearly always one of two mistakes — the environment name
    is wrong, or the file for it was never created — and saying which of those
    is the case saves the reader from guessing.
    """
    if SETTINGS_FILE.exists():
        return f"ENVIRONMENT={ENVIRONMENT}, reading {SETTINGS_FILE.name}"
    return (f"ENVIRONMENT={ENVIRONMENT}, but {SETTINGS_FILE.name} does not "
            f"exist and the value is not set in the environment either")
