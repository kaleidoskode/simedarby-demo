"use client";

/**
 * Keeps a seating plan live.
 *
 * The lifecycle is the whole point of the demo:
 *
 *   1. open the WebSocket, which sends a `snapshot` of the full plan
 *   2. apply each `seat_change` as it arrives, advancing `version`
 *   3. if the socket drops, reconnect and replay everything missed with
 *      `?since={version}` before resuming
 *   4. heartbeat while seats are held, so a hold does not lapse at 120s while
 *      the user is still choosing
 *
 * Step 3 is why the backend logs changes to a Redis stream instead of using
 * pub/sub: a stream can be replayed, so a client that was disconnected can ask
 * for exactly what it missed rather than refetching the whole plan.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, seatSocketUrl } from "@/lib/api";
import type {
  RealtimeMessage,
  SeatChange,
  SeatPlan,
  SeatState,
} from "@/lib/types";

export type ConnectionState = "connecting" | "live" | "reconnecting" | "offline";

/** Refresh holds well inside the 120s server TTL. */
const HEARTBEAT_MS = 45_000;
const RECONNECT_DELAY_MS = 1_500;

type UseSeatPlan = {
  plan: SeatPlan | null;
  connection: ConnectionState;
  error: string | null;
  /** Seats this tab currently holds, in selection order. */
  mySeats: string[];
  /** Seats that just changed, for a brief highlight. */
  recentlyChanged: Set<string>;
  refresh: () => Promise<void>;
};

/** Apply one change to a plan, returning a new plan. */
function applyChange(plan: SeatPlan, change: SeatChange): SeatPlan {
  return {
    ...plan,
    rows: plan.rows.map((row) => {
      if (!change.seat.startsWith(row.row)) return row;
      return {
        ...row,
        seats: row.seats.map((seat) =>
          seat.seat === change.seat
            ? { ...seat, status: change.status, held_by_me: change.held_by_me }
            : seat,
        ),
      };
    }),
    summary: recount(plan, change),
  };
}

/** Keep the counts in step without walking every row twice. */
function recount(plan: SeatPlan, change: SeatChange): SeatPlan["summary"] {
  const previous = plan.rows
    .flatMap((row) => row.seats)
    .find((seat) => seat.seat === change.seat);

  if (!previous || previous.status === change.status) return plan.summary;

  const summary = { ...plan.summary };
  summary[previous.status] -= 1;
  summary[change.status] += 1;
  return summary;
}

export function useSeatPlan(
  showtimeId: string | null,
  token: string | null,
): UseSeatPlan {
  const [plan, setPlan] = useState<SeatPlan | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [recentlyChanged, setRecentlyChanged] = useState<Set<string>>(new Set());

  // Held in refs because the socket callbacks close over them and must always
  // see the latest value without re-subscribing.
  const versionRef = useRef<string>("0-0");
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByUsRef = useRef(false);

  const markChanged = useCallback((seats: string[]) => {
    setRecentlyChanged(new Set(seats));
    setTimeout(() => setRecentlyChanged(new Set()), 1200);
  }, []);

  /** Replay anything that happened while the socket was down. */
  const catchUp = useCallback(async () => {
    if (!showtimeId || versionRef.current === "0-0") return;
    try {
      const missed = await api.getSeatChanges(
        showtimeId,
        versionRef.current,
        token,
      );
      if (missed.changes.length === 0) return;

      setPlan((current) =>
        current ? missed.changes.reduce(applyChange, current) : current,
      );
      versionRef.current = missed.version;
      markChanged(missed.changes.map((change) => change.seat));
    } catch {
      // A failed catch-up is not fatal: the next snapshot corrects everything.
    }
  }, [showtimeId, token, markChanged]);

  const refresh = useCallback(async () => {
    if (!showtimeId) return;
    try {
      const fresh = await api.getSeatPlan(showtimeId, token);
      setPlan(fresh);
      versionRef.current = fresh.version;
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load seats");
    }
  }, [showtimeId, token]);

  useEffect(() => {
    if (!showtimeId) return;

    closedByUsRef.current = false;

    const connect = () => {
      setConnection((current) =>
        current === "live" ? "reconnecting" : current,
      );

      const socket = new WebSocket(seatSocketUrl(showtimeId, token));
      socketRef.current = socket;

      socket.onopen = () => {
        setConnection("live");
        setError(null);
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as RealtimeMessage;

        if (message.type === "snapshot") {
          setPlan(message.plan);
          versionRef.current = message.version;
          return;
        }

        setPlan((current) =>
          current ? message.changes.reduce(applyChange, current) : current,
        );
        versionRef.current = message.version;
        markChanged(message.changes.map((change) => change.seat));
      };

      socket.onerror = () => {
        setError("Lost the live connection to the seating plan");
      };

      socket.onclose = () => {
        if (closedByUsRef.current) return;

        setConnection("reconnecting");
        reconnectRef.current = setTimeout(() => {
          // Catch up first so the gap is filled, then reopen the socket.
          void catchUp().finally(connect);
        }, RECONNECT_DELAY_MS);
      };
    };

    connect();

    return () => {
      closedByUsRef.current = true;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [showtimeId, token, catchUp, markChanged]);

  const mySeats = useMemo(
    () =>
      plan
        ? plan.rows
            .flatMap((row) => row.seats)
            .filter((seat: SeatState) => seat.held_by_me)
            .map((seat) => seat.seat)
        : [],
    [plan],
  );

  // Keep the holds alive while the user deliberates.
  useEffect(() => {
    if (!showtimeId || !token || mySeats.length === 0) return;

    const timer = setInterval(() => {
      void api.heartbeat(showtimeId, mySeats, token).catch(() => {
        // A lapsed hold arrives as a seat_change; nothing to do here.
      });
    }, HEARTBEAT_MS);

    return () => clearInterval(timer);
  }, [showtimeId, token, mySeats]);

  return { plan, connection, error, mySeats, recentlyChanged, refresh };
}
