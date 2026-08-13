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
| Swagger UI | http://localhost:20015/docs |
| OpenAPI schema | http://localhost:20015/openapi.json |
| Health check | http://localhost:20015/health |

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
├── main.py                  # app factory, lifespan, health check
├── workers.py               # gunicorn worker class (WebSocket enabled)
├── core/
│   ├── config.py            # settings, Mongo/Redis/MySQL URI construction
│   └── construct_services.py# dependency injection for services
├── databases/
│   ├── mongodb/             # catalog, bookings, seat reservations
│   ├── redis/               # seat locks, event stream
│   └── mysql/               # retained from the base, lazily initialised
├── routes/cinema/           # HTTP and WebSocket endpoints
├── services/cinema/         # booking logic
├── schemas/cinema/          # domain models
├── seed/                    # wireframe dataset + seeder
├── middleware/              # exception handling, process time logging
└── helpers/ · utilities/ · classes/
```

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
| `app/databases/mysql/db.py` | Engines built lazily | `Database()` ran at import time, so a deployment without MySQL credentials raised `ValueError` before the app could start |
| `app/databases/mysql/config.py` | URI map resolved lazily | Same reason: the class body called `Settings().mysql_config` at import |
| `app/databases/mongodb/config.py` | URI map resolved lazily, added `close()` | Consistency, and clean shutdown |
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

The base shipped a demo module unrelated to cinema booking, which has been
deleted rather than left dead in the tree: `routes/fs/`, `services/fs_services.py`,
`schemas/fs_schema.py` and `classes/fs.py`. The last of these was an SFTP
client requiring `paramiko`, a dependency this service has no use for.
`core/construct_services.py` existed only to wire that module and is now the
injection point for the booking services.
