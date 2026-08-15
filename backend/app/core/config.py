from app.core.environment import ENVIRONMENT, describe_source
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict
from urllib.parse import quote_plus

# Importing app.core.environment has already loaded `.env` and the
# `.env.<environment>` file it names into the process environment, so
# everything below reads from there. Nothing else needs to call load_dotenv.


# Connection schemes accepted for MongoDB.
#   mongodb+srv -> Atlas / any deployment discovered through DNS SRV records
#   mongodb     -> a directly addressed host, e.g. the local docker container
_MONGO_SCHEMES = ("mongodb", "mongodb+srv")

# A standalone mongod cannot honour retryable writes, so the two schemes need
# different default options. Overridable through MONGO1_OPTIONS.
_MONGO_DEFAULT_OPTIONS = {
    "mongodb+srv": "retryWrites=true&w=majority",
    "mongodb": "authSource=admin",
}


def _required(name: str) -> str:
    """Read a setting that the service cannot start without.

    The error names the variable *and* where it was looked for, because the
    two ways to get this wrong — pointing `ENVIRONMENT` at a file that does not
    exist, and a file that exists but is missing a line — need different fixes
    and are otherwise indistinguishable from a stack trace.
    """
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is not set. {describe_source()}")
    return value


class Settings(BaseSettings):
    """Application settings class for handling configuration and environment variables."""

    # Define settings fields with defaults
    root_path: str = ""
    logging_level: str = "INFO"

    # --- Cinema booking API ---------------------------------------------
    title: str = "Cinema Booking API"
    version: str = "1.0.0"

    # Stateless caller identity. Every request carries a self-describing JWT,
    # so no session state is held server side and any worker can serve any
    # request.
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "cinema-booking-api"
    jwt_audience: str = "cinema-booking-client"
    jwt_ttl_seconds: int = 3600

    # Seat lock lifecycle. A seat is held for seat_lock_ttl_seconds while the
    # user is on the seating plan, extended to checkout_lock_ttl_seconds once
    # they enter checkout. Both are TTLs, so an abandoned app frees its seats
    # without any sweeper job.
    seat_lock_ttl_seconds: int = 120
    checkout_lock_ttl_seconds: int = 600
    max_seats_per_booking: int = 10

    # Money is held in minor units (sen for MYR) as integers, never floats,
    # so totals cannot drift through rounding.
    currency: str = "MYR"
    service_charge_minor: int = 50  # RM0.50

    # Screenings are stored in UTC and rendered in the cinema's local time, so
    # a client in another timezone still sees the correct listing.
    cinema_timezone: str = "Asia/Kuala_Lumpur"

    # Catalogue paging
    default_page_size: int = 20
    max_page_size: int = 100

    # Read from the process environment, which `app.core.environment` has
    # already populated from the right file. No `env_file` here on purpose: it
    # would be resolved relative to the working directory rather than to the
    # backend root, so the same code would behave differently depending on
    # where it was launched from.
    model_config = SettingsConfigDict(extra="ignore", env_prefix="APP_")

    @property
    def environment(self) -> str:
        """The deployment environment: local, development or production.

        Set by `ENVIRONMENT` in `.env`, which also decides which
        `.env.<environment>` file the settings above were read from.
        """
        return ENVIRONMENT

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def expose_error_debug(self) -> bool:
        """Whether error responses may carry a stack trace.

        Tracebacks reveal file paths and internal structure, so they are
        withheld in production and returned everywhere else to keep local
        debugging convenient.
        """
        return not self.is_production

    @staticmethod
    def _build_mongo_uri(credentials: Dict[str, str]) -> str:
        """Assemble a MongoDB URI from credentials for the active scheme."""
        scheme = os.getenv("MONGO1_SCHEME", "mongodb+srv").strip()
        if scheme not in _MONGO_SCHEMES:
            raise ValueError(
                f"Unsupported MONGO1_SCHEME '{scheme}'. "
                f"Expected one of: {', '.join(_MONGO_SCHEMES)}"
            )

        options = os.getenv("MONGO1_OPTIONS", _MONGO_DEFAULT_OPTIONS[scheme])

        # Credentials are percent encoded so passwords containing reserved
        # characters (@ : / ?) cannot corrupt the URI.
        username = quote_plus(credentials["username"])
        password = quote_plus(credentials["password"])

        uri = f"{scheme}://{username}:{password}@{credentials['host']}/"
        return f"{uri}?{options}" if options else uri

    @property
    def mongo_config(self) -> Dict[str, str]:
        """Constructs the MongoDB URI and returns it along with the database name.

        The variables carry no environment suffix — `MONGO1_HOST` is the host
        for whichever environment `.env` selected, because the file it was read
        from is what distinguishes them.
        """
        credentials = {
            'username': _required("MONGO1_USER"),
            'password': _required("MONGO1_PASSWORD"),
            'host': _required("MONGO1_HOST"),
            'db': _required("MONGO1_DB"),
        }

        return {credentials['db']: self._build_mongo_uri(credentials)}

    @property
    def redis_config(self) -> Dict[str, str]:
        """Constructs the Redis URI used for seat locks and the event stream.

        Authentication is optional — Redis commonly runs without it on a
        private network — so only the host is required.
        """
        host = _required("REDIS1_HOST")

        username = os.getenv("REDIS1_USER") or ''
        password = os.getenv("REDIS1_PASSWORD") or ''
        if password:
            auth = f"{quote_plus(username)}:{quote_plus(password)}@"
        elif username:
            auth = f"{quote_plus(username)}@"
        else:
            auth = ""

        db_index = os.getenv("REDIS1_DB") or '0'
        scheme = os.getenv("REDIS1_SCHEME", "redis").strip()

        return {'url': f"{scheme}://{auth}{host}/{db_index}"}


# Create the settings instance, ensuring .env values and defaults are loaded
settings = Settings()
