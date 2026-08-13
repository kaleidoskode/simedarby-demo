import os
from dotenv import load_dotenv
load_dotenv()


def environment(env, service):
    """Return credentials for a service in the given environment.

    Kept from the base template: which credential set is read is selected by
    SYSTEM_ENV, so the same image runs locally, in development and in
    production with only the environment changing.
    """
    if (service == "redis1"):
        # Redis backs the seat locks and the real-time event stream.
        # Authentication is optional, so only the host is required here.
        username = None
        password = None
        host = None
        db = os.getenv("REDIS1_DB", "0")
        if (env == "local"):
            username = os.getenv("REDIS1_USER_LOCAL")
            password = os.getenv("REDIS1_PASSWORD_LOCAL")
            host = os.getenv("REDIS1_HOST_LOCAL")
        elif (env == "development"):
            username = os.getenv("REDIS1_USER_DEV")
            password = os.getenv("REDIS1_PASSWORD_DEV")
            host = os.getenv("REDIS1_HOST_DEV")
        elif (env == "production"):
            username = os.getenv("REDIS1_USER_PROD")
            password = os.getenv("REDIS1_PASSWORD_PROD")
            host = os.getenv("REDIS1_HOST_PROD")
        if not host:
            raise ValueError("Redis host environment variable is not set.")

        return {
            'username': username,
            'password': password,
            'host': host,
            'db': db
        }

    elif (service == "mongo1"):
        username = None
        password = None
        host = None
        db = os.getenv("MONGO1_DB")
        if (env == "local"):
            username = os.getenv("MONGO1_USER_LOCAL")
            password = os.getenv("MONGO1_PASSWORD_LOCAL")
            host = os.getenv("MONGO1_HOST_LOCAL")
        elif (env == "development"):
            username = os.getenv("MONGO1_USER_DEV")
            password = os.getenv("MONGO1_PASSWORD_DEV")
            host = os.getenv("MONGO1_HOST_DEV")
        elif (env == "production"):
            username = os.getenv("MONGO1_USER_PROD")
            password = os.getenv("MONGO1_PASSWORD_PROD")
            host = os.getenv("MONGO1_HOST_PROD")
        if not host:
            raise ValueError(
                f"MongoDB host is not set for SYSTEM_ENV='{env}'.")

        return {
            'username': username,
            'password': password,
            'host': host,
            'db': db
        }
