from app.utilities.db_credential_check import credential_check
from app.utilities.prefered_environment import environment
from dotenv import load_dotenv
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict
from urllib.parse import quote_plus

# Load environment variables from .env file
load_dotenv()


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

    # Pydantic configuration: read from .env, ignore extra environment variables
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_prefix="APP_")

    @property
    def system_env(self) -> str:
        """The deployment environment: local, development or production."""
        return os.getenv("SYSTEM_ENV", "development")

    @property
    def is_production(self) -> bool:
        return self.system_env == "production"

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
        """Constructs the MongoDB URI and returns it along with the database name."""
        try:
            # Fetch credentials for different MongoDB databases
            mongo_credentials_1 = environment(self.system_env, 'mongo1')

            # Validate Mongo credentials using the external `credential_check` function
            credential_check([mongo_credentials_1])

            # Simplified return with just the database name and its URL
            return {
                mongo_credentials_1['db']: self._build_mongo_uri(mongo_credentials_1)
            }
        except KeyError as e:
            raise ValueError(
                f"Missing required MongoDB configuration key: {e}")
        except Exception as e:
            raise ValueError(f"Error constructing MongoDB URI: {e}")

    @property
    def redis_config(self) -> Dict[str, str]:
        """Constructs the Redis URI used for seat locks and the event stream."""
        try:
            redis_credentials_1 = environment(self.system_env, 'redis1')

            # Redis commonly runs without authentication in local development,
            # so only the host is mandatory here.
            if not redis_credentials_1.get('host'):
                raise ValueError("Redis host is not set.")

            username = redis_credentials_1.get('username') or ''
            password = redis_credentials_1.get('password') or ''
            if password:
                auth = f"{quote_plus(username)}:{quote_plus(password)}@"
            elif username:
                auth = f"{quote_plus(username)}@"
            else:
                auth = ""

            db_index = redis_credentials_1.get('db') or '0'
            scheme = os.getenv("REDIS1_SCHEME", "redis").strip()

            return {
                'url': f"{scheme}://{auth}{redis_credentials_1['host']}/{db_index}"
            }
        except KeyError as e:
            raise ValueError(f"Missing required Redis configuration key: {e}")
        except Exception as e:
            raise ValueError(f"Error constructing Redis URI: {e}")


# Create the settings instance, ensuring .env values and defaults are loaded
settings = Settings()
