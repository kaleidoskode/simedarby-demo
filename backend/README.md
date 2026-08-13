# Cinema Booking API

Backend for the cinema booking app assignment (section 4.3). The key feature is
locking a seat on a **first come first serve** basis and showing every other
user that seating plan change in real time.

Built on the provided FastAPI base structure: `route -> construct_services
dependency -> service -> datastore`, with `GenericResponse` envelopes and the
`CustomErrorException` middleware.

---

## Running it

```bash
cp .env.example .env
docker compose up --build
```

Then open:

| What | URL |
| --- | --- |
| Swagger UI | http://localhost:8000/docs |
| OpenAPI schema | http://localhost:8000/openapi.json |
| Health check | http://localhost:8000/health |

`/health` reports the reachability of each datastore and returns `503` when
either is unavailable:

```json
{
  "status": "healthy",
  "service": "cinema-booking-api",
  "version": "1.0.0",
  "dependencies": { "mongodb": "up", "redis": "up" }
}
```

### Seeding the demo data

```bash
docker compose exec api python -m app.seed --reset
```

The dataset follows the wireframes structurally — the A–H seating plan with the
same crossed-out seats, the 9:20AM–9:20PM screenings, the combo line-up — but
is localised to Malaysia: GSC Mid Valley Megamall, TGV Sunway Pyramid and GSC
Gurney Plaza across Kuala Lumpur, Selangor and Penang, priced in MYR, with
screening times computed in `Asia/Kuala_Lumpur`. The design shows Nigerian
cinemas and naira, which would read oddly in a Malaysian product.

The seeder prints the demo `showtime_id` and re-derives the Booking Summary
total, so a drift in seed prices is caught immediately rather than noticed
against the design later:

```
Tickets           RM50.00     seats F4, F5 @ RM25.00
Food & Bev        RM54.00     Fresh XL Combo, 10% off RM60.00
Service charge     RM0.50
Total            RM104.50     matches the wireframe breakdown
```

Prices are in **MYR**, held as integer minor units (sen). The wireframe is
priced in naira, where a ticket is ₦2,500; the same figures are used at
Malaysian scale, so a ticket is RM25.00 and the ₦10,450 total reads as
RM104.50. The breakdown is unchanged, only the scale.

Screenings are generated for the next 7 days relative to the run date. The
design shows November 2021, and screenings fixed to a past month would be
filtered out by every showtime query, so only the times of day are taken
literally.

Note that the image copies the source at build time, so `docker compose up -d
--build` is needed for code changes to reach the container.

### Running without Docker

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# point MONGO1_HOST_LOCAL / REDIS1_HOST_LOCAL at localhost in .env, then:
python -m app.main
```

---

## Endpoints

All responses use the `{success, message, data}` envelope. Full schemas at
`/docs`.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/token` | – | Issue a guest token |
| GET | `/api/v1/auth/me` | bearer | Resolve the caller from the token |
| GET | `/api/v1/movies` | – | List or search movies (`q`, `section`, paging) |
| GET | `/api/v1/movies/{id}` | – | Movie detail |
| GET | `/api/v1/movies/{id}/reviews` | – | Star breakdown plus reviews |
| GET | `/api/v1/locations` | – | Location dropdown |
| GET | `/api/v1/cinemas` | – | Cinema dropdown (`location_id`, `q`) |
| GET | `/api/v1/halls/{id}` | – | Physical seat layout |
| GET | `/api/v1/showtimes` | – | Screenings (`movie_id`, `cinema_id`, `date`) |
| GET | `/api/v1/fnb` | – | Food and beverage (`category`) |

The catalogue is public because the design opens onto the home screen with no
login. A token is required from seat locking onward, where a request owns
something and must prove it.

### Getting a token

```bash
curl -X POST localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' -d '{"name":"Raymond"}'
```

In Swagger, paste the returned `access_token` into **Authorize**.

No session is stored. The token carries `sub`, `name`, `iss`, `aud`, `iat` and
`exp`, and is verified on each request with the algorithm pinned to HS256 —
accepting whatever the token declares is how `alg: none` and HS/RS confusion
attacks work.

### Times and dates

Screenings are stored in UTC and served as timezone-aware instants
(`2026-08-14T01:20:00Z`), alongside a `display_time` already rendered in the
cinema's timezone. `?date=YYYY-MM-DD` is the date as the user sees it on the
date strip and is resolved to a local-day window, so an evening screening is
not pushed into the next day by a UTC comparison. Screenings that have already
started are excluded unless `include_past=true`.

---

## Architecture

```
                      +-----------------------------+
   HTTP + WS -------->|  routes/cinema/*.py         |
                      +--------------+--------------+
                                     |  Depends(...)
                      +--------------v--------------+
                      |  services/cinema/*.py       |
                      +------+---------------+------+
                             |               |
                 +-----------v-----+  +------v-------------+
                 | MongoDB         |  | Redis              |
                 | SOURCE OF TRUTH |  | EPHEMERAL          |
                 | catalog,        |  | seat locks (TTL),  |
                 | bookings,       |  | event stream       |
                 | seat_reservations| | (fanout + replay)  |
                 +-----------------+  +--------------------+
```

Redis is **not** trusted for the final booking. It holds the short lived
"someone is choosing this seat" lock. The permanent guarantee is a unique
compound index on `(showtime_id, seat)` in `seat_reservations`, so double
booking stays impossible even if Redis is flushed or restarted.

---

## Project structure

```
app/
├── main.py                    # app factory, lifespan, health check
├── workers.py                 # gunicorn worker class (WebSocket enabled)
├── core/
│   ├── config.py              # settings, Mongo/Redis/MySQL URI construction
│   ├── construct_services.py  # dependency injection for services
│   └── security.py            # JWT mint and verify, caller identity
├── databases/
│   ├── mongodb/               # catalogue, bookings, seat reservations
│   └── redis/                 # seat locks, event stream
├── routes/                    # HTTP and WebSocket endpoints
│   ├── auth.py  movies.py  venues.py  fnb.py
├── services/                  # query and booking logic
│   ├── auth_services.py  catalog_services.py
├── schemas/                   # domain models
│   ├── common_schema.py  auth_schema.py  movie_schema.py
│   ├── cinema_schema.py  fnb_schema.py   booking_schema.py
├── seed/                      # wireframe dataset + seeder
├── middleware/                # exception handling, process time logging
└── helpers/ · utilities/      # response envelope, credential resolution
```

Routes, services and schemas are flat. The service has one domain, so a
`cinema/` package inside each would have added a directory level without ever
holding a second sibling.

### Collections

| Collection | Holds | Notable index |
| --- | --- | --- |
| `movies` | Catalogue | text index on title + synopsis for search |
| `reviews` | Customer reviews | by movie, most recent first |
| `locations` · `cinemas` · `halls` | Venues and seat layouts | cinema by location, hall by cinema |
| `showtimes` | Screenings | by movie and by cinema, both with start time |
| `fnb_items` | Food and drink | by category |
| `bookings` | Booking lifecycle | unique reference; status + expiry |
| `seat_reservations` | Permanently sold seats | **unique `(showtime_id, seat)`** |

That last index is the guarantee behind first come first serve. A Redis lock
stops two users reaching checkout for the same seat, but a lock can be lost to
a restart or an eviction. The unique index makes a seat impossible to sell
twice inside the database itself, whatever the application layer believed:

```
insert a second reservation for a sold seat
  -> E11000 duplicate key error (uniq_showtime_seat)
the same seat on a different showtime
  -> accepted, so the constraint is scoped to the screening
```

---

## Changes made to the base template

The base could not start or build as handed over. Each change below was needed
to get a running stack; the original files and patterns are otherwise intact.

| File | Change | Why |
| --- | --- | --- |
| `app/databases/mongodb/config.py` | URI map resolved lazily, added `close()` | Avoids requiring credentials at import time, and gives a clean shutdown |
| `app/databases/mongodb/db.py` | `tz_aware=True` on the client | The driver returns naive datetimes by default, so a screening serialised as `2026-08-14T01:20:00` with no designator and a client would read it as local time |
| `app/core/config.py` | `MONGO1_SCHEME` / `MONGO1_OPTIONS`, Redis config, JWT and lock settings | The URI was hardcoded to `mongodb+srv://`, which needs DNS SRV records and cannot address a local container |
| `app/utilities/prefered_environment.py` | Added the `redis1` credential branch | Follows the existing per environment credential pattern |
| `app/middleware/exception.py` | Stack trace withheld in production | Every `500` returned a traceback in a `debug` field, exposing internal paths |
| `app/workers.py` | **Added** | `gunicorn_conf.py` referenced `app.workers.ConfigurableWorker`, which did not exist, so the Docker entrypoint failed on start |
| `Dockerfile` | Debian slim, no `.env` / key COPY | The build copied `.data/*.key` files that are not in the repo, so it failed; Alpine also had no wheels for the old dependency set |
| `requirements.txt` | Trimmed to what is used | `nipype`, `pyxnat`, `pymupdf`, `pdfplumber`, `kafka-python` and others pulled a scientific stack unrelated to this service and would not build |
| `.gitignore` | `tests/*` no longer ignored | The concurrency test suite is part of the deliverable |
| `app/main.py` | Cinema identity, lifespan, dependency aware health check | Replaced the template scaffold |
| `pyproject.toml` | Renamed and dependencies aligned | Still declared the template project name and the removed packages |
| `uv.lock` | **Removed** | Locked the trimmed dependency set and contradicted `requirements.txt`, which is what the image installs |

### Removed template scaffolding

The base carried a demo file-server module and a set of utilities this service
never calls. All of it has been deleted rather than left dead in the tree, so
that everything present is something the booking flow actually uses.

| Removed | Was |
| --- | --- |
| `routes/fs/` · `services/fs_services.py` · `schemas/fs_schema.py` · `classes/fs.py` | A demo file server; the last of these an SFTP client needing `paramiko` |
| `databases/mysql/` · `models/password_models.py` | A password-management schema for a database this service never opens |
| `utilities/jwt_verifier.py` | RS256 verification, superseded by `core/security.py` |
| `utilities/mongo_dynamic_connection.py` · `utilities/mysql_dynamic_connection.py` | Multi-tenant connection switching, never called |
| `utilities/custom_exception_handler.py` | Superseded by the exception middleware |
| `utilities/generic_response.py` | A duplicate of the one in `helpers/`, which is the one imported |
| `utilities/logger.py` | Configured logging on import, but nothing imported it |
| `schemas/app_schema.py` | An enum of unrelated application codes |

Dropping the MySQL layer also took `sqlalchemy` and `pymysql` out of the
dependency list. `core/construct_services.py` existed only to wire the demo
module and is now the injection point for the booking services.
