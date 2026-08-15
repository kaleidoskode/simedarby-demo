"""WebSocket endpoint for live seating plan updates.

This is the transport that answers the scenario in 1.0: while User 1 is looking
at the seating plan, User 2 takes A3, and User 1's screen must show it
immediately rather than on the next refresh.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.security import decode_token
from app.databases.mongodb.dependencies import get_mongo_db1
from app.databases.redis.dependencies import get_redis
from app.middleware.exception import CustomErrorException
from app.services.event_services import EventServices
from app.services.lock_services import LockServices
from app.services.realtime_services import broadcaster
from app.services.seat_services import SeatServices

logger = logging.getLogger(__name__)

router = APIRouter()

# Close codes, from the WebSocket specification's private range.
_POLICY_VIOLATION = 1008
_INTERNAL_ERROR = 1011


@router.websocket("/showtimes/{showtime_id}")
async def seating_plan_socket(
    websocket: WebSocket,
    showtime_id: str,
    token: Optional[str] = Query(
        default=None,
        description="Access token. Passed as a query parameter because the "
                    "browser WebSocket API cannot set request headers."),
):
    """Live seat state for one screening.

    Connect to `/api/v1/ws/showtimes/{showtime_id}`. A token is optional: the
    plan is watchable anonymously, and supplying one only makes the caller's own
    holds arrive with `held_by_me` set, which is what the design renders as
    Selected.

    The server sends a `snapshot` first, so a client never has to call the REST
    plan endpoint separately, then a `seat_change` for every subsequent change:

    ```
    {"type": "snapshot", "version": "1723531200000-0", "plan": { ... }}
    {"type": "seat_change", "version": "1723531200000-1",
     "changes": [{"seat": "A3", "status": "locked", "held_by_me": false,
                  "at": "2026-08-13T07:45:24Z"}]}
    ```

    Every message carries the `version` it advances to. If the connection
    drops, reconnect and pass that value to
    `GET /showtimes/{id}/seats/changes?since=` to collect what was missed; the
    WebSocket and that endpoint read the same log, so they cannot disagree.
    That endpoint answers **410** if the client was away long enough for its
    position to fall off the bounded log, meaning the gap cannot be filled and
    the plan should be refetched instead.
    """
    viewer_id = ""
    if token:
        try:
            viewer_id = decode_token(token)["sub"]
        except CustomErrorException as exc:
            # Reject before accepting, so a bad token cannot hold a connection.
            await websocket.close(code=_POLICY_VIOLATION, reason=exc.message)
            return

    await websocket.accept()

    mongo_db = await get_mongo_db1()
    redis = await get_redis()
    events = EventServices(redis)
    seats = SeatServices(mongo_db, LockServices(redis), events)

    try:
        plan = await seats.get_plan(showtime_id, viewer_id=viewer_id)
    except CustomErrorException as exc:
        await websocket.close(code=_POLICY_VIOLATION, reason=exc.message)
        return
    except Exception:
        logger.exception("Failed to build seating plan for %s", showtime_id)
        await websocket.close(code=_INTERNAL_ERROR)
        return

    await websocket.send_json({
        "type": "snapshot",
        "version": plan.version,
        "plan": plan.model_dump(mode="json"),
    })

    # Subscribe from the snapshot's version so nothing between building the
    # snapshot and subscribing is lost.
    await broadcaster.subscribe(showtime_id, websocket, viewer_id,
                                plan.version)
    logger.info("Watching %s: %d viewer(s) on this worker", showtime_id,
                broadcaster.viewer_count(showtime_id))

    try:
        # Nothing is expected from the client; this keeps the connection open
        # and detects the disconnect.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Seating plan socket failed for %s", showtime_id)
    finally:
        await broadcaster.unsubscribe(showtime_id, websocket, viewer_id)
        if websocket.client_state is not WebSocketState.DISCONNECTED:
            await websocket.close()
