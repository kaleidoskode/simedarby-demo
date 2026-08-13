"use client";

/** Booking Confirmation — the last node of the flowchart. */

import { useParams } from "next/navigation";

import { SecondaryButton } from "@/components/ui";

export default function ConfirmationPage() {
  const { bookingId } = useParams<{ bookingId: string }>();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-8 text-center">
      <div className="flex h-28 w-28 items-center justify-center rounded-full bg-surface-raised text-5xl">
        ✓
      </div>

      <h1 className="mt-8 text-2xl font-semibold">Congratulations!</h1>
      <p className="mt-3 text-xs leading-relaxed text-muted">
        Your ticket purchase is successful, a confirmation has been sent to your
        e-mail
      </p>

      <div className="mt-10 flex w-full gap-3">
        <SecondaryButton href="/">← Main menu</SecondaryButton>
        <SecondaryButton href={`/bookings/${bookingId}/ticket`}>
          View ticket
        </SecondaryButton>
      </div>
    </main>
  );
}
