"use client";

/**
 * The seating plan, and the reason this demo exists.
 *
 * Four visual states, from three API values plus one flag:
 *
 *   available            selectable
 *   locked + held_by_me  Selected, this tab holds it
 *   locked               someone else is choosing it, right now
 *   booked               sold
 *
 * The middle two are the same `status` from the server. Splitting them by
 * `held_by_me` is what the design's legend needs, and it is why the API
 * resolves that flag per recipient rather than broadcasting who holds what.
 */

import type { ConnectionState } from "@/hooks/useSeatPlan";
import type { SeatPlan, SeatState } from "@/lib/types";

const STATE_STYLES: Record<string, string> = {
  available:
    "bg-surface-raised text-transparent hover:bg-[#3a3a3d] cursor-pointer",
  mine: "bg-accent text-white cursor-pointer",
  taken: "bg-[#3a2f2f] text-[#8a5a5a] cursor-not-allowed",
  booked: "bg-transparent text-[#4a4a4d] cursor-not-allowed",
};

function styleFor(seat: SeatState): string {
  if (seat.status === "booked") return STATE_STYLES.booked;
  if (seat.status === "locked") {
    return seat.held_by_me ? STATE_STYLES.mine : STATE_STYLES.taken;
  }
  return STATE_STYLES.available;
}

export function SeatGrid({
  plan,
  connection,
  recentlyChanged,
  pending,
  onToggle,
}: {
  plan: SeatPlan;
  connection: ConnectionState;
  recentlyChanged: Set<string>;
  pending: Set<string>;
  onToggle: (seat: SeatState) => void;
}) {
  // Rows A and H hold six seats where the others hold eight, so the grid is
  // sized to the widest row and short rows centre themselves.
  const widest = Math.max(...plan.rows.map((row) => row.seats.length));

  return (
    <div className="px-4 py-2">
      <Legend connection={connection} />

      {/* The curved screen at the top of the design. */}
      <div className="mx-auto mt-6 mb-1 h-6 w-4/5 rounded-t-[50%] bg-gradient-to-b from-[#3a3a3d] to-transparent" />
      <p className="mb-6 text-center text-[10px] uppercase tracking-[0.3em] text-muted">
        Screen
      </p>

      <div className="space-y-1.5">
        {plan.rows.map((row) => (
          <div key={row.row} className="flex items-center gap-2">
            <span className="w-4 shrink-0 text-center text-[11px] text-muted">
              {row.row}
            </span>

            <div
              className="grid flex-1 justify-center gap-1.5"
              style={{
                gridTemplateColumns: `repeat(${widest}, minmax(0, 1fr))`,
              }}
            >
              {/* Inset short rows so the block stays centred. */}
              {row.seats.length < widest && (
                <span style={{ gridColumn: `span ${(widest - row.seats.length) / 2}` }} />
              )}

              {row.seats.map((seat) => {
                const disabled =
                  seat.status === "booked" ||
                  (seat.status === "locked" && !seat.held_by_me) ||
                  pending.has(seat.seat);

                return (
                  <button
                    key={seat.seat}
                    type="button"
                    disabled={disabled}
                    onClick={() => onToggle(seat)}
                    title={`${seat.seat} — ${
                      seat.status === "locked" && !seat.held_by_me
                        ? "being chosen by someone else"
                        : seat.status
                    }`}
                    aria-label={`Seat ${seat.seat}, ${seat.status}`}
                    className={`aspect-square rounded text-[9px] font-medium transition-all ${styleFor(
                      seat,
                    )} ${recentlyChanged.has(seat.seat) ? "seat-changed" : ""} ${
                      pending.has(seat.seat) ? "animate-pulse opacity-60" : ""
                    }`}
                  >
                    {seat.status === "booked" ? "✕" : seat.number}
                  </button>
                );
              })}
            </div>

            <span className="w-4 shrink-0 text-center text-[11px] text-muted">
              {row.row}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Legend({ connection }: { connection: ConnectionState }) {
  const connectionLabel: Record<ConnectionState, { text: string; className: string }> = {
    live: { text: "live", className: "bg-emerald-500" },
    connecting: { text: "connecting", className: "bg-amber-500 animate-pulse" },
    reconnecting: { text: "reconnecting", className: "bg-amber-500 animate-pulse" },
    offline: { text: "offline", className: "bg-red-500" },
  };
  const state = connectionLabel[connection];

  return (
    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-[11px] text-muted">
      <LegendKey className="bg-surface-raised" label="Available" />
      <LegendKey className="bg-accent" label="Selected" />
      <LegendKey className="bg-[#3a2f2f]" label="Being chosen" />
      <LegendKey className="border border-[#4a4a4d] bg-transparent" label="Sold" />

      <span className="flex items-center gap-1.5">
        <span className={`h-2 w-2 rounded-full ${state.className}`} />
        {state.text}
      </span>
    </div>
  );
}

function LegendKey({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-3 w-3 rounded ${className}`} />
      {label}
    </span>
  );
}
