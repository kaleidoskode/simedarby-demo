"use client";

/**
 * View ticket.
 *
 * `qr_payload` is the booking reference alone, so scanning it at the door is a
 * lookup rather than a credential that could be forged from its contents. It is
 * rendered as text here; a real client would draw the QR code.
 */

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  ErrorNote,
  PosterPlaceholder,
  ScreenHeader,
  SecondaryButton,
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import type { Ticket } from "@/lib/types";

export default function TicketPage() {
  const { bookingId } = useParams<{ bookingId: string }>();
  const { session } = useSession();

  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    api
      .getTicket(bookingId, session.token)
      .then(setTicket)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load the ticket"),
      );
  }, [bookingId, session]);

  if (error) return <ErrorNote message={error} />;
  if (!ticket) return <Spinner label="Loading ticket…" />;

  return (
    <main className="min-h-screen">
      <ScreenHeader title="Your ticket" />

      <div className="p-4">
        <section className="overflow-hidden rounded-xl border border-border bg-surface">
          <div className="flex gap-3 p-4">
            <PosterPlaceholder className="h-28 w-20 shrink-0" />
            <div className="min-w-0">
              <h2 className="text-base font-semibold leading-tight">
                {ticket.movie_title}
              </h2>
              <p className="mt-1 text-[11px] text-muted">{ticket.cinema_name}</p>
              <p className="text-[11px] text-muted">{ticket.hall_name}</p>
              <p className="mt-2 text-[11px] text-muted">
                {ticket.ticket_class} · {ticket.seats.length}{" "}
                {ticket.seats.length === 1 ? "seat" : "seats"}
              </p>
            </div>
          </div>

          <div className="relative border-t border-dashed border-border">
            <span className="absolute -left-2 -top-2 h-4 w-4 rounded-full bg-background" />
            <span className="absolute -right-2 -top-2 h-4 w-4 rounded-full bg-background" />
          </div>

          <dl className="grid grid-cols-2 gap-y-3 p-4 text-xs">
            <Cell label="Date" value={ticket.display_date} />
            <Cell label="Seat" value={ticket.seats.join(", ")} />
            <Cell label="Start" value={ticket.start_display} />
            <Cell label="End" value={ticket.end_display} />
            <Cell label="Paid" value={ticket.total_paid.display} span />
          </dl>

          <div className="border-t border-border p-5 text-center">
            <div className="mx-auto flex h-32 w-32 items-center justify-center rounded-lg bg-foreground text-black">
              <span className="px-2 text-center font-mono text-[10px] leading-tight">
                {ticket.qr_payload}
              </span>
            </div>
            <p className="mt-3 font-mono text-sm font-semibold tracking-wider">
              {ticket.reference}
            </p>
            <p className="mt-1 text-[10px] text-muted">
              Show this at the door
            </p>
          </div>
        </section>

        <div className="mt-4">
          <SecondaryButton href="/">← Main menu</SecondaryButton>
        </div>
      </div>
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
