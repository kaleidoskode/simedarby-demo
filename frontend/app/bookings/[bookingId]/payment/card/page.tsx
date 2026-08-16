"use client";

/**
 * Card payment.
 *
 * The card is typed, sent once and forgotten; the API keeps only the last four
 * digits. The idempotency key is generated once per booking attempt and kept in
 * state, so pressing Pay twice — or a retry after a lost response — returns the
 * original charge instead of billing again.
 */

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  BottomBar,
  ErrorNote,
  PrimaryButton,
  ScreenHeader,
  Spinner,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import type { Booking } from "@/lib/types";

/** The shape the API accepts: two digits, a slash, two digits. */
const EXPIRY = /^\d{2}\/\d{2}$/;

/**
 * Insert the slash as the user types, so "1111" becomes "11/11".
 *
 * Nobody should have to type punctuation to satisfy a format. Without this the
 * field accepts "1111", which looks finished and is rejected by the server for
 * not being MM/YY — a round trip to learn something the form knew all along.
 *
 * Typing the slash yourself still works, and so does pasting "12/29": every
 * non-digit is stripped before the separator is put back in one known place.
 */
function formatExpiry(input: string): string {
  let digits = input.replace(/\D/g, "").slice(0, 4);

  // No month starts with 2 through 9, so a lone "3" can only mean March.
  // Filling the zero in saves the user discovering that "3" then "9" gives a
  // month of 39.
  if (digits.length === 1 && digits > "1") digits = `0${digits}`;

  return digits.length <= 2 ? digits : `${digits.slice(0, 2)}/${digits.slice(2)}`;
}

export default function CardPaymentPage() {
  const { bookingId } = useParams<{ bookingId: string }>();
  const router = useRouter();
  const { session } = useSession();

  const [booking, setBooking] = useState<Booking | null>(null);
  const [number, setNumber] = useState("");
  const [expiry, setExpiry] = useState("");
  const [cvv, setCvv] = useState("");
  const [saveCard, setSaveCard] = useState(false);
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // One key for this visit to the payment screen, not one per click, so
  // pressing Pay twice returns the original charge instead of billing again.
  // Lazy initial state rather than a ref written during render, which would be
  // a side effect in the render phase.
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    if (!session) return;
    api
      .getBooking(bookingId, session.token)
      .then(setBooking)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load the booking"),
      );
  }, [bookingId, session]);

  const pay = async () => {
    if (!session) return;
    setPaying(true);
    setError(null);
    try {
      await api.pay(
        bookingId,
        { method: "debit_card", card: { number, expiry, cvv },
          save_card: saveCard },
        session.token,
        idempotencyKey,
      );
      router.push(`/bookings/${bookingId}/confirmation`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 402) {
        setError(`${cause.message} Try 4242 4242 4242 4242.`);
      } else {
        setError(cause instanceof Error ? cause.message : "Payment failed");
      }
      setPaying(false);
    }
  };

  if (!booking && !error) return <Spinner label="Loading…" />;

  const ready =
    number.replace(/\D/g, "").length >= 13 && EXPIRY.test(expiry) && cvv.length >= 3;

  return (
    <main className="flex min-h-screen flex-col">
      <ScreenHeader title="Card payment" />

      <div className="flex-1 p-4">
        <p className="text-xs text-muted">Please enter your card details</p>

        <label className="mt-5 block text-[11px] text-muted">Card number</label>
        <input
          value={number}
          onChange={(event) => setNumber(event.target.value)}
          placeholder="Enter card number"
          inputMode="numeric"
          autoComplete="off"
          className="mt-1.5 w-full rounded-lg border border-border bg-surface-raised px-3 py-3 text-sm outline-none placeholder:text-muted focus:border-accent"
        />

        <div className="mt-4 grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] text-muted">Expiry date</label>
            <input
              value={expiry}
              onChange={(event) => setExpiry(formatExpiry(event.target.value))}
              placeholder="MM/YY"
              inputMode="numeric"
              maxLength={5}
              autoComplete="off"
              className="mt-1.5 w-full rounded-lg border border-border bg-surface-raised px-3 py-3 text-sm outline-none placeholder:text-muted focus:border-accent"
            />
          </div>
          <div>
            <label className="block text-[11px] text-muted">CVV2</label>
            <input
              value={cvv}
              onChange={(event) => setCvv(event.target.value)}
              placeholder="Enter CVV"
              inputMode="numeric"
              autoComplete="off"
              className="mt-1.5 w-full rounded-lg border border-border bg-surface-raised px-3 py-3 text-sm outline-none placeholder:text-muted focus:border-accent"
            />
          </div>
        </div>

        {error && <ErrorNote message={error} />}

        <label className="mt-5 flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={saveCard}
            onChange={(event) => setSaveCard(event.target.checked)}
            className="h-4 w-4 accent-white"
          />
          Save card info for future transactions
        </label>

        <div className="mt-6 rounded-lg border border-border bg-surface p-3 text-[11px] text-muted">
          <p className="font-medium text-foreground">Test cards</p>
          <p className="mt-1">
            <span className="font-mono">4242 4242 4242 4242</span> succeeds
          </p>
          <p>
            <span className="font-mono">4000 0000 0000 0002</span> is declined
          </p>
          <p className="mt-1">
            Expiry <span className="font-mono">MM/YY</span>, any future date —
            try <span className="font-mono">12/29</span> — and a 3-digit CVV.
          </p>
        </div>
      </div>

      <BottomBar>
        <PrimaryButton onClick={pay} disabled={!ready || paying}>
          {paying
            ? "Processing…"
            : `Pay   ${booking?.amounts.total.display ?? ""}`}
        </PrimaryButton>
      </BottomBar>
    </main>
  );
}
