"use client";

/**
 * A strip identifying which guest this browser tab is.
 *
 * Not part of the product. It exists so that in a two-window demonstration it
 * is obvious the windows are different people: without it, "the other user
 * locked A3" is a claim the audience has to take on trust.
 */

import { useSession } from "@/lib/SessionProvider";

export function DemoToolbar() {
  const { session, loading, reissue } = useSession();

  return (
    <div className="sticky top-0 z-50 border-b border-border bg-[#0b0b0c]/95 backdrop-blur">
      <div className="mx-auto flex max-w-[430px] items-center gap-3 px-4 py-2 text-xs">
        <span className="rounded bg-surface-raised px-2 py-1 font-medium text-muted">
          demo
        </span>

        <span className="min-w-0 flex-1 truncate font-mono text-muted">
          {loading && "identifying…"}
          {!loading && session && (
            <>
              <span className="text-foreground">{session.user.name}</span>
              <span className="text-muted"> · {session.user.id}</span>
            </>
          )}
          {!loading && !session && (
            <span className="text-red-400">API unreachable</span>
          )}
        </span>

        <button
          type="button"
          onClick={() => void reissue()}
          disabled={loading}
          className="shrink-0 rounded border border-border px-2 py-1 text-muted transition hover:border-accent hover:text-foreground disabled:opacity-40"
          title="Become a different guest, so this tab races the other one"
        >
          new identity
        </button>
      </div>
    </div>
  );
}
