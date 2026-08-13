"use client";

/**
 * Select payment method.
 *
 * `requires_card` decides whether the card form comes next, which is the only
 * branch in the design's payment flow. The other two methods confirm directly.
 */

import { useRouter } from "next/navigation";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorNote, ScreenHeader, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import type { PaymentMethodOption } from "@/lib/types";

const ICONS: Record<string, string> = {
  debit_card: "▭",
  bank_transfer: "🏛",
  crypto_wallet: "◈",
};

export default function PaymentMethodPage() {
  const { bookingId } = useParams<{ bookingId: string }>();
  const router = useRouter();
  const { session } = useSession();

  const [methods, setMethods] = useState<PaymentMethodOption[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listPaymentMethods()
      .then(setMethods)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load methods"),
      );
  }, []);

  const choose = async (method: PaymentMethodOption) => {
    if (method.requires_card) {
      router.push(`/bookings/${bookingId}/payment/card`);
      return;
    }

    if (!session) return;
    setBusy(method.id);
    setError(null);
    try {
      // A key per attempt, so a retry after a dropped response returns the
      // original charge rather than billing again.
      await api.pay(
        bookingId,
        { method: method.id },
        session.token,
        crypto.randomUUID(),
      );
      router.push(`/bookings/${bookingId}/confirmation`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Payment failed");
      setBusy(null);
    }
  };

  return (
    <main className="min-h-screen">
      <ScreenHeader title="Payment" />

      <div className="p-4">
        <p className="text-xs text-muted">
          How would you like to make the payment? Kindly select your preferred option
        </p>

        {error && <ErrorNote message={error} />}
        {!methods && !error && <Spinner label="Loading methods…" />}

        <div className="mt-4 overflow-hidden rounded-xl border border-border bg-surface">
          {methods?.map((method, index) => (
            <button
              key={method.id}
              type="button"
              disabled={busy !== null}
              onClick={() => void choose(method)}
              className={`flex w-full items-center gap-3 px-4 py-4 text-left transition hover:bg-surface-raised disabled:opacity-50 ${
                index > 0 ? "border-t border-border" : ""
              }`}
            >
              <span className="w-6 text-center text-lg text-muted">
                {ICONS[method.id]}
              </span>
              <span className="flex-1">
                <span className="block text-sm font-medium">{method.label}</span>
                <span className="block text-[11px] text-muted">
                  {method.description}
                </span>
              </span>
              <span className="text-muted">
                {busy === method.id ? "…" : "›"}
              </span>
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
