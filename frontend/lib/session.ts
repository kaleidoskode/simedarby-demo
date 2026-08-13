/**
 * Guest identity for the demo.
 *
 * The API issues a token per guest and holds no session, so the client keeps
 * the token and that is the whole session.
 *
 * Identity is stored in **sessionStorage, not localStorage**, and that choice
 * is what makes the demo work: sessionStorage is per browser tab, so opening
 * the seating plan in two tabs gives two different users racing for the same
 * seat. localStorage is shared across tabs, which would make both windows the
 * same person and quietly defeat the thing being demonstrated.
 */

import { api } from "./api";
import type { CurrentUser } from "./types";

const TOKEN_KEY = "cinema.token";
const USER_KEY = "cinema.user";

export type Session = {
  token: string;
  user: CurrentUser;
};

const GUEST_NAMES = [
  "Raymond", "Aisyah", "Wei Ming", "Rajesh", "Nurul",
  "Farid", "Mei Ling", "Hafiz", "Priya", "Daniel",
];

function randomName(): string {
  return GUEST_NAMES[Math.floor(Math.random() * GUEST_NAMES.length)];
}

export function readSession(): Session | null {
  if (typeof window === "undefined") return null;

  const token = sessionStorage.getItem(TOKEN_KEY);
  const user = sessionStorage.getItem(USER_KEY);
  if (!token || !user) return null;

  try {
    return { token, user: JSON.parse(user) as CurrentUser };
  } catch {
    return null;
  }
}

function writeSession(session: Session): void {
  sessionStorage.setItem(TOKEN_KEY, session.token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(session.user));
}

/** Return the existing identity for this tab, or mint a new one. */
export async function ensureSession(name?: string): Promise<Session> {
  const existing = readSession();
  if (existing) return existing;
  return newSession(name);
}

/** Discard this tab's identity and become someone else. */
export async function newSession(name?: string): Promise<Session> {
  const issued = await api.issueToken(name ?? randomName());
  const session = { token: issued.access_token, user: issued.user };
  writeSession(session);
  return session;
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}
