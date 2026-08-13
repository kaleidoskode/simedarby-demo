"use client";

/**
 * Ticket Booking: choose where and when, then pick seats.
 *
 * Selection and the seating plan are one scrolling screen, matching the design.
 * The seat plan is live: locks by other users arrive over the WebSocket without
 * a refresh, which is the behaviour the whole backend is built around.
 */

import { useRouter } from "next/navigation";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { SeatGrid } from "@/components/SeatGrid";
import {
  BottomBar,
  ErrorNote,
  PrimaryButton,
  ScreenHeader,
  Spinner,
} from "@/components/ui";
import { useSeatPlan } from "@/hooks/useSeatPlan";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import type {
  CinemaSummary,
  Location,
  SeatState,
  ShowtimeSummary,
} from "@/lib/types";

/** The date strip in the design shows a week. */
function nextDays(count: number): { iso: string; weekday: string; day: string }[] {
  return Array.from({ length: count }, (_, offset) => {
    const date = new Date();
    date.setDate(date.getDate() + offset);
    return {
      iso: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
        date.getDate(),
      ).padStart(2, "0")}`,
      weekday: date.toLocaleDateString("en-GB", { weekday: "short" }),
      day: String(date.getDate()),
    };
  });
}

export default function BookingPage() {
  const { movieId } = useParams<{ movieId: string }>();
  const router = useRouter();
  const { session } = useSession();
  const token = session?.token ?? null;

  const days = useMemo(() => nextDays(7), []);

  const [locations, setLocations] = useState<Location[]>([]);
  const [cinemas, setCinemas] = useState<CinemaSummary[]>([]);
  const [showtimes, setShowtimes] = useState<ShowtimeSummary[]>([]);

  const [locationId, setLocationId] = useState("");
  const [cinemaId, setCinemaId] = useState("");
  const [date, setDate] = useState(days[0].iso);
  const [showtimeId, setShowtimeId] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);

  const { plan, connection, error: planError, mySeats, recentlyChanged, refresh } =
    useSeatPlan(showtimeId, token);

  // Locations, once.
  useEffect(() => {
    api
      .listLocations()
      .then((values) => {
        setLocations(values);
        setLocationId((current) => current || values[0]?.id || "");
      })
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load locations"),
      );
  }, []);

  // Cinemas follow the chosen location.
  useEffect(() => {
    if (!locationId) return;
    api
      .listCinemas(locationId)
      .then((values) => {
        setCinemas(values);
        setCinemaId(values[0]?.id ?? "");
      })
      .catch(() => setCinemas([]));
  }, [locationId]);

  // Screenings follow the cinema and the date. Nothing is cleared
  // synchronously here; when there is no cinema the list is simply derived as
  // empty below, which avoids a cascading render.
  useEffect(() => {
    if (!cinemaId) return;
    let cancelled = false;

    api
      .listShowtimes({ movieId, cinemaId, date })
      .then((values) => {
        if (cancelled) return;
        setShowtimes(values);
        setShowtimeId(null);
      })
      .catch(() => {
        if (!cancelled) setShowtimes([]);
      });

    return () => {
      cancelled = true;
    };
  }, [movieId, cinemaId, date]);

  // Derived rather than stored, so a location with no cinemas cannot leave a
  // stale list of screenings on screen.
  const visibleShowtimes = cinemaId ? showtimes : [];

  const toggleSeat = useCallback(
    async (seat: SeatState) => {
      if (!showtimeId || !token) return;

      setConflict(null);
      setPending((current) => new Set(current).add(seat.seat));

      try {
        if (seat.held_by_me) {
          await api.releaseSeats(showtimeId, [seat.seat], token);
        } else {
          await api.lockSeats(showtimeId, [seat.seat], token);
        }
        // The resulting change arrives over the socket, so nothing is applied
        // here: one path updates the grid, whoever caused it.
      } catch (cause) {
        if (cause instanceof ApiError) {
          setConflict(cause.message);
          // A conflict means the local view is stale; the authoritative plan
          // settles it.
          if (cause.status === 409) void refresh();
        }
      } finally {
        setPending((current) => {
          const next = new Set(current);
          next.delete(seat.seat);
          return next;
        });
      }
    },
    [showtimeId, token, refresh],
  );

  const proceed = async () => {
    if (!showtimeId || !token || mySeats.length === 0) return;
    setCreating(true);
    setConflict(null);
    try {
      const booking = await api.createBooking(showtimeId, mySeats, token);
      router.push(`/bookings/${booking.id}/fnb`);
    } catch (cause) {
      setConflict(cause instanceof Error ? cause.message : "Could not start the booking");
      setCreating(false);
    }
  };

  const selectedShowtime = visibleShowtimes.find((showtime) => showtime.id === showtimeId);
  const subtotal =
    selectedShowtime && mySeats.length
      ? mySeats.length * selectedShowtime.price.minor
      : 0;

  if (error) return <ErrorNote message={error} />;

  return (
    <main className="flex min-h-screen flex-col">
      <ScreenHeader title="Ticket Booking" />

      <div className="flex-1 px-4 pb-6">
        <p className="pt-4 text-xs text-muted">
          Where would you like to see the movie? Kindly select as appropriate
        </p>

        <Field label="Location">
          <select
            value={locationId}
            onChange={(event) => setLocationId(event.target.value)}
            className="w-full rounded-lg border border-border bg-surface px-3 py-3 text-sm outline-none focus:border-accent"
          >
            {locations.map((location) => (
              <option key={location.id} value={location.id}>
                {location.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Cinema Hall">
          <select
            value={cinemaId}
            onChange={(event) => setCinemaId(event.target.value)}
            className="w-full rounded-lg border border-border bg-surface px-3 py-3 text-sm outline-none focus:border-accent"
          >
            {cinemas.length === 0 && <option>No cinemas here</option>}
            {cinemas.map((cinema) => (
              <option key={cinema.id} value={cinema.id}>
                {cinema.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Select a date">
          <div className="flex gap-2 overflow-x-auto pb-1">
            {days.map((day) => (
              <button
                key={day.iso}
                type="button"
                onClick={() => setDate(day.iso)}
                className={`flex min-w-[52px] shrink-0 flex-col items-center rounded-lg border px-2 py-2 text-xs transition ${
                  date === day.iso
                    ? "border-foreground bg-surface-raised"
                    : "border-border text-muted hover:border-accent"
                }`}
              >
                <span className="text-[10px]">{day.weekday}</span>
                <span className="font-semibold">{day.day}</span>
              </button>
            ))}
          </div>
        </Field>

        <Field label="Available Time">
          {visibleShowtimes.length === 0 ? (
            <p className="text-xs text-muted">
              No screenings left today. Try another date.
            </p>
          ) : (
            <div className="grid grid-cols-4 gap-2">
              {visibleShowtimes.map((showtime) => (
                <button
                  key={showtime.id}
                  type="button"
                  onClick={() => setShowtimeId(showtime.id)}
                  className={`rounded-lg border px-1 py-2 text-[11px] transition ${
                    showtimeId === showtime.id
                      ? "border-foreground bg-surface-raised font-semibold"
                      : "border-border text-muted hover:border-accent"
                  }`}
                >
                  {showtime.display_time}
                </button>
              ))}
            </div>
          )}
        </Field>

        {showtimeId && (
          <div className="mt-6 border-t border-border pt-4">
            <h2 className="mb-1 text-center text-sm font-semibold">Select Seat</h2>

            {planError && <ErrorNote message={planError} onRetry={refresh} />}
            {!plan && !planError && <Spinner label="Loading seats…" />}

            {plan && (
              <SeatGrid
                plan={plan}
                connection={connection}
                recentlyChanged={recentlyChanged}
                pending={pending}
                onToggle={toggleSeat}
              />
            )}

            {conflict && (
              <p className="mt-3 rounded-lg border border-amber-900/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-300">
                {conflict}
              </p>
            )}
          </div>
        )}
      </div>

      {showtimeId && plan && (
        <BottomBar>
          <div className="mb-3 flex items-center justify-between rounded-lg border border-border px-3 py-2 text-xs">
            <div>
              <p className="text-[10px] uppercase tracking-wide text-muted">Seat</p>
              <p className="font-medium">
                {mySeats.length ? mySeats.join(", ") : "—"}
              </p>
            </div>
            <div className="text-right">
              <p className="text-[10px] uppercase tracking-wide text-muted">Sub-total</p>
              <p className="font-semibold">
                {selectedShowtime
                  ? `${selectedShowtime.price.currency === "MYR" ? "RM" : ""}${(
                      subtotal / 100
                    ).toFixed(2)}`
                  : "—"}
              </p>
            </div>
          </div>
          <PrimaryButton
            onClick={proceed}
            disabled={mySeats.length === 0 || creating}
          >
            {creating ? "Starting booking…" : "Proceed"}
          </PrimaryButton>
        </BottomBar>
      )}
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <label className="mb-1.5 block text-xs font-medium">{label}</label>
      {children}
    </div>
  );
}
