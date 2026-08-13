FROM python:3.11-slim

# Debian slim rather than Alpine: the pinned dependencies publish manylinux
# wheels, so nothing has to be compiled from source at build time.

# curl is used by the compose healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install dependencies first so this layer is cached across code changes.
# The test suite is installed too, so a reviewer can run it against the live
# stack with a single command. A production build would install
# requirements.txt alone.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy the application source. Configuration is supplied at run time through
# the compose env_file, so no .env or key material is baked into the image.
COPY . .

# Expose the application on port
EXPOSE ${PORT}

# Command to run the application. The worker class and bind address come from
# gunicorn_conf.py, which reads them from the environment.
ENTRYPOINT ["gunicorn", "-c", "gunicorn_conf.py", "app.main:app"]
