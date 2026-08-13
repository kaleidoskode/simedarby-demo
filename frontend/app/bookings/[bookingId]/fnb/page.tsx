"use client";

/**
 * Beverages & Food, with Skip.
 *
 * The whole order is sent at once with `PUT /bookings/{id}/fnb`, which replaces
 * rather than appends. That matches a screen where quantities are adjusted and
 * then confirmed, and makes the call safe to repeat.
 */

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  BottomBar,
  ErrorNote,
  PosterPlaceholder,
  PrimaryButton,
  ScreenHeader,
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatMinor } from "@/lib/money";
import { useSession } from "@/lib/SessionProvider";
import type { FnbCategory, FnbItem } from "@/lib/types";

const TABS: { id: FnbCategory; label: string }[] = [
  { id: "combo", label: "Combo" },
  { id: "food_snacks", label: "Food/Snacks" },
  { id: "beverages", label: "Beverages" },
];

export default function FnbPage() {
  const { bookingId } = useParams<{ bookingId: string }>();
  const router = useRouter();
  const { session } = useSession();

  const [items, setItems] = useState<FnbItem[] | null>(null);
  const [tab, setTab] = useState<FnbCategory>("combo");
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listFnb()
      .then(setItems)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load the menu"),
      );
  }, []);

  const setQuantity = (id: string, next: number) =>
    setQuantities((current) => ({ ...current, [id]: Math.max(0, next) }));

  const submit = async (skip: boolean) => {
    if (!session) return;
    setSaving(true);
    setError(null);
    try {
      const selection = skip
        ? []
        : Object.entries(quantities)
            .filter(([, quantity]) => quantity > 0)
            .map(([fnb_id, quantity]) => ({ fnb_id, quantity }));

      await api.setFnb(bookingId, selection, session.token);
      router.push(`/bookings/${bookingId}/summary`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save the order");
      setSaving(false);
    }
  };

  const visible = items?.filter((item) => item.category === tab) ?? [];
  // Taken from the catalogue rather than assumed, so the preview cannot
  // claim a currency the items are not priced in.
  const currency = items?.[0]?.price.currency ?? "MYR";
  const totalItems = Object.values(quantities).reduce((sum, n) => sum + n, 0);
  const subtotalMinor =
    items?.reduce(
      (sum, item) => sum + item.price.minor * (quantities[item.id] ?? 0),
      0,
    ) ?? 0;

  return (
    <main className="flex min-h-screen flex-col">
      <ScreenHeader
        title="Beverages & Food"
        action={
          <button
            type="button"
            onClick={() => void submit(true)}
            disabled={saving}
            className="text-xs text-muted transition hover:text-foreground disabled:opacity-40"
          >
            Skip ›
          </button>
        }
      />

      <div className="flex border-b border-border text-sm">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            onClick={() => setTab(entry.id)}
            className={`flex-1 py-3 transition ${
              tab === entry.id
                ? "border-b-2 border-foreground font-medium"
                : "text-muted"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {error && <ErrorNote message={error} />}
      {!items && !error && <Spinner label="Loading menu…" />}

      <div className="grid flex-1 grid-cols-2 gap-3 p-4">
        {visible.map((item) => (
          <article
            key={item.id}
            className={`rounded-lg border border-border bg-surface p-2 ${
              item.is_available ? "" : "opacity-50"
            }`}
          >
            <div className="relative">
              <PosterPlaceholder className="aspect-[4/3] w-full" />
              {item.discount_pct && (
                <span className="absolute right-1 top-1 rounded bg-foreground px-1.5 py-0.5 text-[9px] font-semibold text-black">
                  {item.discount_pct}% off
                </span>
              )}
            </div>

            <p className="mt-2 text-xs font-medium">{item.name}</p>
            <p className="mt-0.5 line-clamp-2 text-[10px] text-muted">
              {item.description}
            </p>

            <div className="mt-2 flex items-center justify-between">
              <div className="text-xs">
                {item.original_price && (
                  <span className="mr-1 text-[10px] text-muted line-through">
                    {item.original_price.display}
                  </span>
                )}
                <span className="font-semibold">{item.price.display}</span>
              </div>

              {item.is_available ? (
                <div className="flex items-center gap-1.5">
                  <Stepper
                    label="−"
                    onClick={() => setQuantity(item.id, (quantities[item.id] ?? 0) - 1)}
                  />
                  <span className="w-4 text-center text-xs">
                    {quantities[item.id] ?? 0}
                  </span>
                  <Stepper
                    label="+"
                    onClick={() => setQuantity(item.id, (quantities[item.id] ?? 0) + 1)}
                  />
                </div>
              ) : (
                <span className="text-[9px] uppercase text-muted">sold out</span>
              )}
            </div>
          </article>
        ))}
      </div>

      <BottomBar>
        <div className="mb-3 flex items-center justify-between rounded-lg border border-border px-3 py-2 text-xs">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-muted">Item</p>
            <p className="font-medium">{totalItems}</p>
          </div>
          <div className="text-right">
            <p className="text-[10px] uppercase tracking-wide text-muted">Sub-total</p>
            <p className="font-semibold">{formatMinor(subtotalMinor, currency)}</p>
          </div>
        </div>
        <PrimaryButton onClick={() => void submit(false)} disabled={saving}>
          {saving ? "Saving…" : "Confirm"}
        </PrimaryButton>
      </BottomBar>
    </main>
  );
}

function Stepper({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="h-5 w-5 rounded border border-border text-xs leading-none text-muted transition hover:border-accent hover:text-foreground"
    >
      {label}
    </button>
  );
}
