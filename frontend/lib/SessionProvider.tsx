"use client";

/**
 * Makes the guest identity available to every screen.
 *
 * The token is minted on first mount rather than on the server, because the
 * identity is per browser tab and the server has no idea which tab is asking.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { ensureSession, newSession, type Session } from "./session";

type SessionContextValue = {
  session: Session | null;
  loading: boolean;
  /** Become a different guest, for demonstrating two users in two tabs. */
  reissue: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue>({
  session: null,
  loading: true,
  reissue: async () => {},
});

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    ensureSession()
      .then((value) => {
        if (!cancelled) setSession(value);
      })
      .catch(() => {
        // The API being unreachable is reported by the screens themselves;
        // failing here would leave the whole app blank.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const reissue = useCallback(async () => {
    setLoading(true);
    try {
      setSession(await newSession());
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <SessionContext.Provider value={{ session, loading, reissue }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  return useContext(SessionContext);
}
