# Cinema Booking API — Sime Darby developer assignment

Submission for **section 4.3, Back End Developer**.

The brief's key feature is locking a seat on a **first come first serve** basis
and showing that change to everyone else in real time. That is what this is
built around, and what the material below is arranged to let you verify.

```
backend/     the submission — a FastAPI service, MongoDB and Redis
frontend/    a proof of concept, not part of the assessment
```

---

## Start here

```bash
cd backend
cp .env.example .env
docker compose up --build
docker compose exec api python -m app.seed --reset
```

That is the whole setup. Nothing else to install, no credentials to obtain.

| | |
| --- | --- |
| **Swagger UI** | **http://localhost:8000/docs** |
| OpenAPI schema | http://localhost:8000/openapi.json |
| Health check | http://localhost:8000/health |

### API documentation

4.3 asks for API documentation, preferably Swagger. **http://localhost:8000/docs**
is generated from the code, so it cannot drift from the implementation.

Every endpoint carries a request model, a response model and a description of
*why* it behaves as it does — 23 operations and 64 schemas. It is interactive:
press **Authorize**, paste a token from `POST /api/v1/auth/token`, and the whole
booking flow can be exercised from the browser without any other tool.

`/health` reports whether MongoDB and Redis are reachable and returns `503` if
either is not, so a failure is legible rather than a timeout.

---

## How section 4.3 is met

| Requirement | Where |
| --- | --- |
| Endpoints for the flow at 2.0 | 23 REST operations plus a WebSocket, covering every node from Home to Booking Confirmation — [endpoint table](backend/README.md#endpoints) |
| Statelessness in API design | No session store; a JWT carries identity and all shared state is in Redis and MongoDB, verified across four worker processes — [Statelessness](backend/README.md#statelessness) |
| The best way to cater for the real-time scenario | One Redis stream feeding a WebSocket, with one reader per worker rather than per client — [Real-time updates](backend/README.md#real-time-updates) |
| The best method for real-time booking | Atomic Lua locks with a TTL, backed by a unique index that makes double selling impossible — [Seat locking](backend/README.md#seat-locking) |
| Polling / WebSocket / HTTP2 comparison | WebSocket chosen, polling shipped alongside as a fallback on the same log, HTTP/2 push rejected with reasons — [Transport comparison](backend/README.md#transport-comparison) |
| API documentation | Swagger at `/docs` |

[backend/README.md](backend/README.md) is the detailed write-up: the design
decisions, the collections and indexes, and a table of every change made to the
supplied base template with the reason for each.

---

## Verifying the claims

```bash
docker compose exec api pytest -v          # 57 tests
```

The suite runs against the **live stack over HTTP**, not in process, because
gunicorn serves from four worker processes and a lock that only held within one
event loop would pass a unit test and fail in production.

The headline test fires **50 simultaneous requests for one seat** and asserts
exactly one `201` and forty-nine `409`.

Three guarantees were confirmed by deliberately breaking the code to check the
tests notice: removing the conflict check from the Lua script let all 50 racers
win, disabling the WebSocket fan-out timed out the push tests, and removing the
idempotency guard broke the payment retry test. A fourth mutation *passed*,
which turned out to be more useful — it exposed a rollback bug one layer down.
That story is in [backend/README.md](backend/README.md#tests).

---

## Seeing the seat locking: `frontend/`

**This is a proof of concept for the backend, not a submission.** Section 4.1
asks for a **mobile** app in React Native or Flutter; this is a web app,
deliberately, so it cannot be mistaken for an answer to that track. The
deliverable is the API.

It exists because of one gap. Swagger can demonstrate every endpoint here
except the behaviour the assignment is actually built around: a seat locking
the instant another user takes it. A JSON response cannot show that. Two
browser windows can, in about three seconds.

With the backend already running:

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

Then, to see the scenario described in 1.0:

1. Open **http://localhost:3000** in **two browser windows**, side by side.
2. Each window is a different guest — identity is per browser tab, and the strip
   at the top shows who each one is.
3. In both: **Venom: Let There Be Carnage → Book Ticket →** the date the seeder
   printed **→ 5:40PM**.
4. Click a seat in the left window.

The right window greys that seat immediately, labelled *being chosen*, and
cannot select it. The left shows the same seat blue, as *Selected*. Same seat,
same server state, rendered differently per viewer — which is the three-state
legend in the design.

Nothing is polled: the green *live* dot is a WebSocket, and the network panel
stays quiet while seats change.

The client walks the rest of the flowchart too — search, movie detail, seats,
food, summary, payment, ticket — so the API can be seen working end to end.
Two seats and a Fresh XL Combo come to **RM104.50**, the total printed on the
Booking Summary in the wireframe.

[frontend/README.md](frontend/README.md) has the details, including how to
demonstrate reconnection catch-up by restarting the API mid-session.

---

## Reading the code

If you would rather read than run, these are the files that carry the design:

| File | Why |
| --- | --- |
| [`app/services/lock_services.py`](backend/app/services/lock_services.py) | The Lua seat locks. The comment at the top explains why atomicity, all-or-nothing and holder-only release all fall out of one property |
| [`app/databases/mongodb/indexes.py`](backend/app/databases/mongodb/indexes.py) | The unique `(showtime_id, seat)` index — the guarantee Redis is *not* trusted for |
| [`app/services/realtime_services.py`](backend/app/services/realtime_services.py) | WebSocket fan-out, one Redis reader per worker rather than per client |
| [`app/services/payment_services.py`](backend/app/services/payment_services.py) | Claim, reserve, charge, confirm — in that order, and why |
| [`tests/test_seat_lock_concurrency.py`](backend/tests/test_seat_lock_concurrency.py) | The 50-way race and the rest of the locking guarantees |

---

## Deliberate omissions

Stated so the scope is explicit rather than inferred: the payment gateway is
simulated, there are no user accounts, and there is no rate limiting. The
reasoning for each is in
[backend/README.md](backend/README.md#not-built).
