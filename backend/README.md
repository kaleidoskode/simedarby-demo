# Cinema Booking API

Backend for the cinema booking app assignment, **section 4.3 (Back End
Developer)**. The key feature is locking a seat on a **first come first serve**
basis and showing every other user that change to the seating plan in real
time.

Built on the provided FastAPI base structure: `route -> construct_services
dependency -> service -> datastore`, with `GenericResponse` envelopes and the
`CustomErrorException` middleware.

```bash
cp .env.example .env
docker compose up --build
docker compose exec api python -m app.seed --reset
docker compose exec api pytest -v
```

Swagger is then at **http://localhost:8000/docs**.

---

## How this meets 4.3

| Requirement | Where | In short |
| --- | --- | --- |
| Build the API endpoints for the flow at 2.0 | [Endpoints](#endpoints) | 23 REST operations and 1 WebSocket, covering every node of the flowchart from Home through to Booking Confirmation |
| Demonstrate statelessness in API design | [Statelessness](#statelessness) | No session store. Callers carry a JWT, all shared state is in Redis and MongoDB, so any worker serves any request — verified across 4 gunicorn workers |
| The best way to cater for the real-time scenario | [Real-time updates](#real-time-updates) | One Redis stream feeding a WebSocket, with one reader per worker rather than per client. Proven to cross worker processes |
| The best method for real-time booking scenarios | [Seat locking](#seat-locking) · [Payment](#payment) | Atomic Lua locks with a TTL, backed by a unique index that makes double selling impossible. 50 simultaneous requests for one seat produce exactly one winner |
| Polling / WebSocket / HTTP2 comparison | [Transport comparison](#transport-comparison) | WebSocket chosen, polling shipped alongside as a fallback reading the same log, HTTP/2 push rejected with reasons |
| API documentation, e.g. Swagger UI | `/docs` | Auto-generated OpenAPI, 64 schemas, every endpoint with request and response models |

Beyond the brief: a **59-test suite** run against the live stack, three of whose
guarantees were confirmed by deliberately breaking the code to check the tests
notice. See [Tests](#tests).

---

## Running it

Docker is the only prerequisite. From a clone of the repository:

```bash
cd backend
cp .env.example .env       # config; the defaults work as shipped
docker compose up --build  # api on :8000, plus MongoDB and Redis
```

`.env` is not committed, so it is copied from the template. The service refuses
to start without it rather than booting with placeholder credentials.

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

The API starts with an empty database, so this is required before there is
anything to browse:

```bash
docker compose exec api python -m app.seed --reset
```

`--reset` **drops** the collections rather than emptying them, so indexes are
rebuilt from the current declarations instead of surviving from an earlier
schema. Without the flag the seeder upserts, repairing existing documents and
leaving anything else alone. Either way it is safe to re-run, and it is the way
back to a clean, known state.

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

### Tests

```bash
docker compose exec api pytest -v
```

The suite runs against the live stack over HTTP, not in process. That is
deliberate: gunicorn serves these requests from several worker processes, so a
lock that held only within one event loop would fail here. Testing through the
socket is what proves the guarantee survives horizontal scaling, which is the
reason the lock lives in Redis rather than in memory.

The headline test fires **50 simultaneous requests for one seat** and asserts
exactly one `201` and forty-nine `409`. The rest cover all-or-nothing
selection, holder-only release, TTL expiry, heartbeat behaviour, retry
idempotency and locking a sold seat. The real-time tests cover push delivery to
one and to several watchers, per-recipient `held_by_me`, and that polling
returns the identical change at the identical version.

The booking and payment tests check the arithmetic against the design: two
seats and a discounted combo come to **RM104.50**, the total printed on the
Booking Summary screen and on the ticket.

The suites were verified to actually fail when they should, by breaking the
code they cover:

* removing the conflict check from the Lua script let all 50 racers win the
  same seat, and the concurrency test caught it
* disabling the fan-out made the five push-dependent real-time tests time out,
  while the six that do not need push still passed
* removing the idempotency guard made the payment retry test fail

One mutation was more informative for passing. Removing the atomic claim from
the payment path did **not** break anything: twelve concurrent payments still
produced a single charge, because the unique index on `seat_reservations` is
what actually serialises them. That prompted a closer look at the rollback,
which was deleting reservations by `booking_id` — too broad if two requests for
one booking ever reserved at the same time, since a losing request would delete
rows the winner had just written. It now removes only the ids the failing
attempt itself inserted.

```
tests/test_booking_flow.py .......................
tests/test_payment_flow.py .................
tests/test_realtime.py .............
tests/test_seat_lock_concurrency.py ..........
59 passed
```

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
| GET | `/api/v1/showtimes/{id}/seats` | optional | Seating plan with live seat state |
| GET | `/api/v1/showtimes/{id}/seats/changes` | optional | Changes since a version (polling fallback) |
| WS | `/api/v1/ws/showtimes/{id}` | optional | Live seat changes, pushed |
| POST | `/api/v1/showtimes/{id}/seats/lock` | bearer | Hold seats, all or nothing |
| DELETE | `/api/v1/showtimes/{id}/seats/lock` | bearer | Release your own holds |
| POST | `/api/v1/showtimes/{id}/seats/lock/heartbeat` | bearer | Extend a hold |
| GET | `/api/v1/fnb` | – | Food and beverage (`category`) |
| POST | `/api/v1/bookings` | bearer | Start a booking from held seats |
| GET | `/api/v1/bookings` | bearer | List your bookings |
| GET | `/api/v1/bookings/{id}` | bearer | Booking summary |
| PUT | `/api/v1/bookings/{id}/fnb` | bearer | Set the food and drink order |
| DELETE | `/api/v1/bookings/{id}` | bearer | Cancel and release the seats |
| GET | `/api/v1/payment-methods` | – | Payment options |
| POST | `/api/v1/bookings/{id}/pay` | bearer | Pay and confirm the seats |
| GET | `/api/v1/bookings/{id}/ticket` | bearer | Ticket for a confirmed booking |

The catalogue is public because the design opens onto the home screen with no
login. A token is required from seat locking onward, where a request owns
something and must prove it.

### Getting a token

```bash
curl -X POST localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' -d '{"name":"Raymond"}'
```

In Swagger, paste the returned `access_token` into **Authorize**.

### Statelessness

Nothing is held in a worker between requests. There is no session store, no
sticky routing and no in-memory cache of anything a later request depends on:

* **Identity** travels in the request. The JWT carries `sub`, `name`, `iss`,
  `aud`, `iat` and `exp`, and is verified on each call with the algorithm
  pinned to HS256 — accepting whatever the token declares is how `alg: none`
  and HS/RS confusion attacks work.
* **Seat holds** live in Redis, not in the process that created them, so the
  worker that locks a seat and the worker that later releases or sells it need
  not be the same one.
* **Real-time state** is a Redis stream. A WebSocket is the one thing that
  necessarily holds a connection, but it holds no authoritative state: it is a
  subscriber, and a client can reconnect to a different worker and catch up
  with `?since=`.

The application runs under **four gunicorn workers** and the suite drives it
over HTTP for exactly that reason — a guarantee that only held inside one event
loop would fail there. The fan-out was checked directly across processes: with
the socket on worker `pid 9` and eight locks handled by `pid 10` and `pid 7`,
none by `pid 9`, the socket still received all eight changes.

The practical consequence is that the service scales by adding workers or
containers, with no shared memory and nothing to drain on deploy.

Guest tokens are issued on demand, so this is identity rather than access
control: it proves *which* caller holds a seat, and stops one user releasing
another's. It does not stop a determined client requesting many tokens — that
is a rate limiting concern, noted under [Not built](#not-built).

### Seat locking

The requirement in 1.0: as User 2 starts booking seat A3, User 1 sees A3 as
locked and can no longer book it.

A lock is one Redis key per seat, holding the owner's id with a TTL:

```
lock:{showtime_id}:{seat} -> "usr_8f2a7c1e"   PX 120000
```

Acquire, release and extend are **Lua scripts**. Redis runs a script to
completion before any other command, which is where three properties come
from at once:

| Property | Why the script gives it |
| --- | --- |
| Nothing interleaves | Checking every seat then claiming them is one indivisible step, so two users racing cannot both see a seat free |
| All or nothing | F4 and F5 are taken together or not at all, so nobody holds half a selection. Per-seat `SET NX` would need rollback, and a crash mid-rollback leaks a lock |
| Holder only | The compare-and-delete is inside the script, so User 2 cannot free User 1's seat between the read and the write |

The TTL is what makes an abandoned app harmless: close it on the seating plan
and the seats free themselves. No sweeper job, no expiry table, nothing
scheduled.

A conflict returns **409** naming exactly which seats lost, so the client
repaints those rather than reloading the plan:

```json
{ "success": false,
  "message": "Someone is already holding: F5",
  "details": { "conflicts": ["F5"], "reason": "locked" } }
```

`held_by_me` on each seat is what separates the design's three states: a locked
seat is *Selected* when it is the caller's own hold and unavailable when it is
someone else's.

**Redis is not the final authority.** It stops two users reaching checkout for
the same seat, but a lock can be lost to a restart or an eviction. The binding
guarantee is the unique index on `(showtime_id, seat)` in MongoDB, applied when
payment is confirmed.

### Bookings

A lock and a booking are separate on purpose, and each does one job:

```
lock      ephemeral   Redis     "I am choosing this seat"
booking   durable     MongoDB   "this is what I intend to buy"
```

A booking can only be created for seats the caller **already holds**, so a
client cannot skip the seating plan and book seats it never locked. Creating
one extends those holds from the short seat-picking TTL to the longer checkout
window, and sets the booking's `expires_at` to match, so the two never disagree
about when the hold ends.

Expiry is resolved when a booking is read, not by a scheduled job. The seats are
already free by then, released by the Redis TTL; this only brings the booking's
status into line, which keeps the service stateless with nothing running in the
background.

`PUT /bookings/{id}/fnb` replaces the whole order rather than appending, which
matches a screen where quantities are adjusted then confirmed and makes the call
idempotent — sending it twice cannot double the order. A quantity of zero
removes an item and an empty list clears it, which is what Skip does. **Prices
come from the catalogue, never from the request**, so a client cannot choose
what it pays.

Cancelling releases the holds immediately and broadcasts the change, so everyone
watching the plan sees the seats reappear instead of waiting out the TTL.

Screening details are copied onto the booking rather than joined at read time,
so the summary and the ticket render from one document and still read correctly
long after the catalogue has moved on.

### Payment

The order of operations is the design, not an implementation detail:

```
1. claim the booking   atomic; a second request cannot claim a claimed booking
2. reserve the seats   unique index binds here; cheap and reversible
3. charge              irreversible, so it goes last
4. confirm
```

Reserving before charging means a seat lost between the summary and the payment
screen costs the user nothing — the request fails with `409` before any money
moves. Charging first would mean taking payment for seats that were never
allocated, which needs a refund to undo.

**Idempotency.** Send an `Idempotency-Key` header. A retry with the same key
returns the original booking and the original transaction reference instead of
charging again, which matters on a mobile network where a response can be lost
after the request already succeeded. Without a key, paying twice is a `409`
rather than a second sale.

**Cards are not stored.** The number is validated (length and Luhn check digit),
used, and discarded; only the last four digits are kept so a user can recognise
which card they used. A real deployment would send the card straight to a
provider and never let it reach this service.

For the simulated gateway, a card ending `0002` or `0000` is declined with
`402`, matching the convention providers use for test numbers, so the failure
path can be exercised. A declined payment leaves the seats held and the booking
retryable with another card — nothing is reserved.

### Real-time updates

Both transports read **one Redis stream**, the same log the lock and release
endpoints append to. That is the point: a WebSocket client and a polling client
cannot end up disagreeing about what happened, because there is only one record
of it.

```
lock / release ──XADD──> stream:showtime:{id}
                              │
              ┌───────────────┴────────────────┐
        XREAD BLOCK                       XRANGE (since
              ▼                                ▼
   WS /api/v1/ws/showtimes/{id}      GET .../seats/changes?since=
```

**A stream, not pub/sub.** Pub/sub is fire and forget: a client that drops its
connection has no way to learn what it missed, and a polling endpoint could not
be built on it at all. Every stream entry has an id, so the same log serves live
push, polling, and reconnect catch-up.

**One reader per worker, not per client.** Giving each socket its own blocking
read would mean 300 Redis connections for 300 people watching one screening.
Each worker keeps a single reader per showtime and fans out to the sockets it
holds locally, so Redis connections scale with screenings being watched, not
viewers.

```
Redis stream ──XREAD BLOCK──> reader task (one per worker per showtime)
                                    │
                        ┌───────────┼───────────┐
                        ▼           ▼           ▼
                     socket      socket      socket
```

Verified across processes: with the socket held by worker **pid 9** and eight
locks handled by workers **pid 10** and **pid 7** — none by pid 9 — the socket
received all eight changes. Delivery goes through Redis, not process memory,
which is why any worker can serve any client.

**Messages.** A `snapshot` arrives first, so a client needs no separate REST
call, then a `seat_change` per change:

```json
{"type": "snapshot", "version": "1786608216915-0", "plan": { ... }}
{"type": "seat_change", "version": "1786608216915-0",
 "changes": [{"seat": "A2", "status": "locked", "held_by_me": false,
              "at": "2026-08-13T08:03:36.915626+00:00"}]}
```

The holder's id is never sent. Whether a change is the caller's own is answered
by `held_by_me`, resolved per recipient, so watching a plan reveals no other
user's identifier.

**Reconnecting.** Every message carries the `version` it advances to. After a
dropped socket, pass the last one seen to
`GET /showtimes/{id}/seats/changes?since=` and collect exactly what was missed
instead of re-fetching the whole plan. The `since` bound is exclusive, so
polling twice never replays a change already applied.

**When the gap is too old to fill.** The log is trimmed at 1,000 entries per
screening, so a client away long enough loses its place in it. Returning
whichever entries happen to have survived would be worse than failing: the
client would believe it had caught up while quietly missing everything that was
trimmed, and the seats on screen would be wrong with nothing to say so. That
case answers **410** with the oldest version still held, and the client refetches
the plan. Sitting exactly on the oldest surviving entry is still served — the
entries after it are by definition intact — so the check costs nothing in the
normal case.

### Transport comparison

| Approach | Latency | Cost per viewer | Verdict |
| --- | --- | --- | --- |
| REST polling on a timer | half the interval on average | a request per viewer per tick | shipped as the fallback |
| Long polling | low | a held connection plus reconnect churn | superseded by WebSocket |
| HTTP/2 server push | n/a | — | rejected: removed from browsers, and it pushes sub-resources rather than application events |
| Server-sent events | low | one connection, one direction | viable, and simpler; rejected only because the booking flow benefits from a duplex channel later |
| **WebSocket** | **low** | **one connection, duplex** | **chosen** |

Polling is kept rather than dismissed. On a mobile network a socket will not
always stay up, and a client that cannot hold one still needs correct data —
which it gets, from the same log.

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
                       +----------------------------+
   HTTP + WS --------->|  app/routes/*.py           |
                       +-------------+--------------+
                                     | Depends(...)  core/construct_services.py
                       +-------------v--------------+
                       |  app/services/*.py         |
                       +------+--------------+------+
                              |              |
                  +-----------v----+  +------v-------------+
                  | MongoDB        |  | Redis              |
                  | SOURCE OF TRUTH|  | EPHEMERAL          |
                  | catalogue,     |  | seat locks (TTL),  |
                  | bookings,      |  | event stream       |
                  | seat_reservations| | (fanout + replay) |
                  +----------------+  +--------------------+
```

Redis is **not** trusted for the final booking. It holds the short lived
"someone is choosing this seat" lock. The permanent guarantee is a unique
compound index on `(showtime_id, seat)` in `seat_reservations`, so double
booking stays impossible even if Redis is flushed or restarted.

The split is the point: losing a lock costs a user a retry, whereas losing a
reservation would sell the same seat twice. Only the second needs durability.

---

## Project structure

```
app/
├── main.py                     app factory, lifespan, health check
├── workers.py                  gunicorn worker class (WebSocket enabled)
├── core/
│   ├── config.py               settings, Mongo and Redis URI construction
│   ├── construct_services.py   dependency injection for every service
│   ├── security.py             JWT mint and verify, caller identity
│   └── logging_config.py       stdout logging, honours APP_LOGGING_LEVEL
├── databases/
│   ├── mongodb/                client, collections, index bootstrap
│   └── redis/                  client and pool
├── routes/
│   ├── auth.py                 guest token, whoami
│   ├── movies.py               catalogue, search, reviews
│   ├── venues.py               locations, cinemas, halls, showtimes
│   ├── fnb.py                  food and beverage catalogue
│   ├── seats.py                seating plan, lock, release, heartbeat, deltas
│   ├── realtime.py             WebSocket endpoint
│   ├── bookings.py             draft bookings and the food order
│   └── payments.py             methods, pay, ticket
├── services/
│   ├── auth_services.py        token issuing
│   ├── catalog_services.py     all read side queries
│   ├── lock_services.py        Redis Lua seat locks
│   ├── event_services.py       the seat change stream
│   ├── seat_services.py        seating plan, composed from three sources
│   ├── realtime_services.py    WebSocket fan-out, one reader per worker
│   ├── booking_services.py     drafts, food order, cancellation
│   └── payment_services.py     payment, reservation, ticket
├── schemas/                    domain models, one module per area
├── seed/                       wireframe dataset and seeder
├── middleware/                 exception handling, process time logging
├── helpers/                    the GenericResponse envelope
└── utilities/                  credential resolution, local time formatting

tests/
├── conftest.py                 fixtures; lock purging between tests
├── test_seat_lock_concurrency.py
├── test_realtime.py
├── test_booking_flow.py
└── test_payment_flow.py
```

Routes, services and schemas are flat. The service has one domain, so a
`cinema/` package inside each would have added a directory level without ever
holding a second sibling.

### Collections

| Collection | Holds | Notable index |
| --- | --- | --- |
| `movies` | Catalogue | title (listing order), sections (home screen rails) |
| `reviews` | Customer reviews | by movie, most recent first |
| `locations` · `cinemas` · `halls` | Venues and seat layouts | cinema by location, hall by cinema |
| `showtimes` | Screenings | by movie and by cinema, both with start time |
| `fnb_items` | Food and drink | by category |
| `bookings` | Booking lifecycle | unique reference; user + recency; status + expiry |
| `seat_reservations` | Permanently sold seats | **unique `(showtime_id, seat)`** |

Search is a case-insensitive substring match, because a search box needs `ven`
to find `Venom` and a text index matches whole words. No index can serve a
substring, so there is deliberately none for it: a text index would have looked
useful without ever being used. At a catalogue size where the scan matters, this
belongs in a dedicated search engine rather than a cleverer Mongo query.

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

## Not built

Deliberate omissions, so the scope is explicit rather than left to be inferred.

| Not built | Why |
| --- | --- |
| Real payment provider | The gateway is simulated. The integration point is one method, `PaymentServices._charge`; everything around it — ordering, idempotency, rollback — is what the flow actually depends on and is real |
| User accounts | The flowchart opens on the Home screen with no login. Identity is a guest token, which is what seat ownership needs; accounts would add a store the design never asks for |
| Rate limiting and seat quotas per user | A booking is capped at 10 seats, but nothing stops a client requesting many tokens. The answer is rate limiting at the edge, not in this service |
| Promo codes | The Booking Summary wireframe shows a Promo Code field, but the 2.0 flowchart that 4.3 refers to has no such step. Left out rather than guessed at |
| Refunds and cancellation after payment | Outside the flowchart, which ends at Booking Confirmation |
| Email or push notifications | The confirmation screen mentions an email; sending it is not a backend API concern for this brief |

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
| `app/main.py` | CORS made the outermost middleware, `allow_credentials=False` | `add_middleware` prepends, so registering the exception handler last put it *outside* CORS and its `4xx` responses never passed back through. Every error reached a browser with no `Access-Control-Allow-Origin` and was blocked, including the `409` naming contested seats. Credentials are off because auth is a bearer header, and pairing them with `allow_origins=["*"]` is invalid |
| `app/workers.py` | **Added** | `gunicorn_conf.py` referenced `app.workers.ConfigurableWorker`, which did not exist, so the Docker entrypoint failed on start |
| `app/core/logging_config.py` | **Added** | Nothing configured logging, so the root logger sat at WARNING with no handlers: every `logger.info` was discarded and `logger.error` escaped only through Python's unformatted fallback, including the middleware's stack traces |
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
