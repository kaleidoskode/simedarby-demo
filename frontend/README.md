# Cinema Booking — demo web client

A small Next.js app that drives the [Cinema Booking API](../backend) through the
whole booking journey.

## This is not a submission for 4.1

Section 4.1 asks for a **mobile** app in React Native or Flutter. This is a web
app, deliberately, so it cannot be mistaken for an answer to that track. The
assessment being answered is **4.3, Back End Developer**, and the deliverable is
the API in [`../backend`](../backend).

This exists because one thing in that API cannot be shown through Swagger: a
seat locking the instant another user takes it. Open the seating plan in two
browser windows and it is obvious in three seconds. Everything else here is
scaffolding to reach that screen honestly, by walking the same flow a real
client would.

## Running it

The API must be up first.

```bash
cd ../backend
cp .env.example .env
docker compose up -d
docker compose exec api python -m app.seed --reset
```

Then either run this directly:

```bash
npm install
npm run dev            # http://localhost:3000
```

or bring it up with the stack, where it sits behind a compose profile so that
someone who only wants the API is not made to wait for a Next.js build:

```bash
cd ../backend
docker compose --profile demo up --build
```

`NEXT_PUBLIC_API_BASE` defaults to `http://localhost:8000`. It is read by the
browser, not the container, so it must be the address the browser can reach —
`http://api:8000` would only resolve inside the compose network.

## Showing the real-time locking

1. Open `http://localhost:3000` in **two browser windows**, side by side.
2. Each window is a different guest. Identity is kept in `sessionStorage`, which
   is per tab, so the two windows are genuinely two people — the strip at the
   top shows who each one is. `localStorage` would have made them the same
   person and quietly defeated the whole demonstration.
3. In both windows: **Venom: Let There Be Carnage → Book Ticket →** pick the
   date the seeder printed **→ 5:40PM**.
4. Click a seat in window A.

Window B greys that seat immediately, labelled *being chosen*, and cannot click
it. Window A shows the same seat blue, as *Selected*. Same seat, same server
state, rendered differently per viewer — which is the three-state legend in the
design, and why the API resolves `held_by_me` per recipient instead of
broadcasting who holds what.

Two further things worth showing:

- **Nothing is polled.** The green *live* dot is a WebSocket. Watch a seat
  change with the network panel open and there are no requests.
- **Reconnection.** `docker compose restart api`, then lock a seat in window A
  while window B is reconnecting. B catches up through
  `GET /seats/changes?since=…` rather than refetching the plan. That is what a
  Redis stream buys over pub/sub, which cannot replay at all.

## The rest of the journey

Home and search → movie detail with ratings → showtime picker → seats → food
and beverage → booking summary → payment → confirmation → ticket. Two seats and
a Fresh XL Combo come to **RM104.50**, the total printed on the Booking Summary
in the design.

On the card screen, `4242 4242 4242 4242` succeeds and `4000 0000 0000 0002` is
declined. A decline leaves the seats held and the booking payable with another
card; nothing is reserved until the charge succeeds.

## How it is put together

```
lib/types.ts        mirrors the API schemas
lib/api.ts          fetch wrapper; unwraps {success, message, data} and turns a
                    failure into a typed ApiError carrying status and details
lib/session.ts      guest identity, per tab
hooks/useSeatPlan   snapshot -> WebSocket -> reconnect catch-up -> heartbeat
components/SeatGrid the four visual states
app/…               one route per node of the 2.0 flowchart
```

Two decisions worth knowing:

**Money is never computed here.** Amounts arrive as integer minor units with a
preformatted `display` string. The client renders what the server says, so
there is exactly one place a total can be wrong.

**A seat click does not update the grid.** It calls the API and waits for the
change to arrive over the socket, the same path another user's change takes.
One code path repaints the grid regardless of who caused the change, so the
holder's view and everyone else's cannot drift apart.

## A bug this found

Building this surfaced a real defect in the API: `ExceptionHandler` was
registered after `CORSMiddleware`, making it the outer middleware, so the
`JSONResponse` it returns for a `4xx` never passed back through CORS. Every
error reached the browser with no `Access-Control-Allow-Origin` and was blocked
— the carefully structured `409` naming the contested seats was unreadable to
exactly the client that needed it. Fixed in `backend/app/main.py`; a browser
was the only thing that would have caught it.
