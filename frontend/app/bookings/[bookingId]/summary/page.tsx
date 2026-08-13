"use client";

/**
 * Booking Summary — the ticket stub and the four money lines.
 *
 * Every amount comes from the API preformatted. The client never does
 * arithmetic on money: the server holds integer minor units and renders the
 * display string, so there is one place a total can be wrong.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  BottomBar,
  ErrorNote,
  PosterPlaceholder,
  ScreenHeader,
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import type { Booking } from "@/lib/types";

export default function SummaryPage() {
  const { bookingId } = useParams<{ bookingId: string }>();
  const { session } = useSession();

  const [booking, setBooking] = useState<Booking | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    api
      .getBooking(bookingId, session.token)
      .then(setBooking)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load the booking"),
      );
  }, [bookingId, session]);

  if (error) return <ErrorNote message={error} />;
  if (!booking) return <Spinner label="Loading summary…" />;

  const { screening, amounts } = booking;
  const hours = Math.floor(screening.duration_mins / 60);
  const minutes = screening.duration_mins % 60;

  return (
    <main className="flex min-h-screen flex-col">
      <ScreenHeader title="Booking Summary" />

      <div className="flex-1 space-y-4 p-4">
        {/* Ticket stub */}
        <section className="overflow-hidden rounded-xl border border-border bg-surface">
          <div className="flex gap-3 p-4">
            <PosterPlaceholder className="h-28 w-20 shrink-0" />
            <div className="min-w-0">
              <h2 className="text-base font-semibold leading-tight">
                {screening.movie_title}
              </h2>
              <p className="mt-1 text-[11px] text-muted">
                {screening.genres.join(", ")}
              </p>
              <p className="text-[11px] text-muted">
                {hours}h {minutes}m
              </p>
              <p className="text-[11px] text-muted">
                {screening.formats.join(", ")}
              </p>
              <p className="text-[11px] text-muted">
                {booking.ticket_class} Tickets
              </p>
            </div>
          </div>

          {/* Perforation */}
          <div className="relative border-t border-dashed border-border">
            <span className="absolute -left-2 -top-2 h-4 w-4 rounded-full bg-background" />
            <span className="absolute -right-2 -top-2 h-4 w-4 rounded-full bg-background" />
          </div>

          <dl className="grid grid-cols-2 gap-y-3 p-4 text-xs">
            <Cell label="Cinema" value={screening.cinema_name} span />
            <Cell label="Date" value={screening.display_date} />
            <Cell label="Seat" value={booking.seats.join(", ")} />
            <Cell label="Start" value={screening.start_display} />
            <Cell label="End" value={screening.end_display} />
          </dl>
        </section>

        {/* Money */}
        <section className="space-y-3 rounded-xl border border-border bg-surface p-4 text-xs">
          <Line
            label="Tickets"
            sub={`${booking.ticket_class} tickets [x${booking.seats.length}]`}
            value={amounts.tickets.display}
          />

          {booking.fnb_items.length > 0 && (
            <Line
              label="Food & Beverage"
              sub={booking.fnb_items
                .map((line) => `${line.name} [x${line.quantity}]`)
                .join(", ")}
              value={amounts.fnb.display}
            />
          )}

          <Line
            label="Charges"
            sub="Service charge"
            value={amounts.service_charge.display}
          />

          <div className="flex items-center justify-between border-t border-border pt-3 text-sm font-semibold">
            <span>Total Amount Payable</span>
            <span>{amounts.total.display}</span>
          </div>
        </section>

        <p className="text-center text-[10px] text-muted">
          Reference {booking.reference} · held until{" "}
          {booking.expires_at
            ? new Date(booking.expires_at).toLocaleTimeString("en-GB", {
                hour: "2-digit",
                minute: "2-digit",
              })
            : "—"}
        </p>
      </div>

      <BottomBar>
        <Link
          href={`/bookings/${booking.id}/payment`}
          className="block w-full rounded-lg bg-foreground px-4 py-3.5 text-center text-sm font-semibold text-black transition hover:bg-white"
        >
          Proceed to payment
        </Link>
      </BottomBar>
    </main>
  );
}

function Cell({
  label,
  value,
  span,
}: {
  label: string;
  value: string;
  span?: boolean;
}) {
  return (
    <div className={span ? "col-span-2" : ""}>
      <dt className="text-[10px] uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 font-medium">{value}</dd>
    </div>
  );
}

function Line({
  label,
  sub,
  value,
}: {
  label: string;
  sub: string;
  value: string;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="font-medium">{label}</p>
        <p className="truncate text-[11px] text-muted">{sub}</p>
      </div>
      <span className="shrink-0 font-semibold">{value}</span>
    </div>
  );
}
