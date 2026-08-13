# Cinema Booking — Sime Darby developer assignment

Submission for **section 4.3, Back End Developer**.

```
backend/     the deliverable — a FastAPI service with the booking API
frontend/    a local demo client, not part of the assessment
```

The two are independent. The backend runs in Docker and knows nothing about the
frontend; the frontend is a development server pointed at it.

## The submission: `backend/`

```bash
cd backend
cp .env.example .env
docker compose up --build
docker compose exec api python -m app.seed --reset
```

| | |
| --- | --- |
| Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Tests | `docker compose exec api pytest -v` |

[backend/README.md](backend/README.md) covers how each requirement in 4.3 is
met, the seat locking design, and the real-time transport comparison.

## The demo: `frontend/`

Section 4.1 asks for a **mobile** app in React Native or Flutter. This is a web
app, deliberately, so it cannot be mistaken for an answer to that track.

It exists because one thing in the API cannot be shown through Swagger: a seat
locking the instant another user takes it. Opened in two browser windows, the
seating plan makes it obvious in seconds.

With the backend already running:

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

It is a dev server on purpose — nothing to build, nothing to containerise, and
nothing extra for a reviewer who only wants the API. See
[frontend/README.md](frontend/README.md) for how to stage the two-window
demonstration.
