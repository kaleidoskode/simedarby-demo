"use client";

/** Small shared pieces, kept together because none is big enough to own a file. */

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

export function ScreenHeader({
  title,
  action,
  back = true,
}: {
  title: string;
  action?: ReactNode;
  back?: boolean;
}) {
  const router = useRouter();

  return (
    <header className="sticky top-[41px] z-40 flex items-center gap-3 border-b border-border bg-background/95 px-4 py-3 backdrop-blur">
      {back && (
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="Go back"
          className="text-xl leading-none text-foreground transition hover:text-accent"
        >
          ←
        </button>
      )}
      <h1 className="flex-1 truncate text-base font-semibold">{title}</h1>
      {action}
    </header>
  );
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="w-full rounded-lg bg-foreground px-4 py-3.5 text-sm font-semibold text-black transition enabled:hover:bg-white disabled:cursor-not-allowed disabled:bg-surface-raised disabled:text-muted"
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  children,
  href,
  onClick,
}: {
  children: ReactNode;
  href?: string;
  onClick?: () => void;
}) {
  const className =
    "block w-full rounded-lg border border-border px-4 py-3.5 text-center text-sm font-semibold text-foreground transition hover:border-accent";

  if (href) {
    return (
      <Link href={href} className={className}>
        {children}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} className={className}>
      {children}
    </button>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-sm text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-foreground" />
      {label}
    </div>
  );
}

export function ErrorNote({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="m-4 rounded-lg border border-red-900/60 bg-red-950/40 p-4 text-sm">
      <p className="text-red-300">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded border border-red-800 px-3 py-1.5 text-xs text-red-200 transition hover:bg-red-900/40"
        >
          Try again
        </button>
      )}
    </div>
  );
}

/** Sticky bottom bar, as every action screen in the design has one. */
export function BottomBar({ children }: { children: ReactNode }) {
  return (
    <div className="sticky bottom-0 border-t border-border bg-background/95 p-4 backdrop-blur">
      {children}
    </div>
  );
}

export function Stars({ value }: { value: number }) {
  return (
    <span className="text-sm tracking-tight" aria-label={`${value} out of 5`}>
      {[1, 2, 3, 4, 5].map((star) => (
        <span key={star} className={star <= Math.round(value) ? "text-foreground" : "text-border"}>
          ★
        </span>
      ))}
    </span>
  );
}

/** Grey block standing in for artwork the API points at but does not host. */
export function PosterPlaceholder({ className = "" }: { className?: string }) {
  return (
    <div
      className={`flex items-center justify-center rounded bg-surface-raised text-[10px] uppercase tracking-widest text-muted ${className}`}
    >
      poster
    </div>
  );
}
