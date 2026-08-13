/**
 * Client for the Cinema Booking API.
 *
 * Every response uses the same `{success, message, data}` envelope, so one
 * wrapper unwraps `data` and turns a failure into a typed error carrying the
 * status and the `details` block. That matters for seat locking: a 409 arrives
 * with `details.conflicts` naming exactly which seats were lost, which is what
 * lets the seating plan repaint those seats instead of reloading.
 */

import type {
  Booking,
  CinemaSummary,
  Envelope,
  FnbCategory,
  FnbItem,
  Location,
  LockResult,
  MovieDetail,
  MovieSection,
  MovieSummary,
  Paged,
  PaymentMethod,
  PaymentMethodOption,
  ReleaseResult,
  ReviewList,
  SeatChangeList,
  SeatPlan,
  ShowtimeSummary,
  Ticket,
  TokenResponse,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const V1 = `${API_BASE}/api/v1`;

export type ApiErrorDetails = {
  conflicts?: string[];
  reason?: string;
  unknown_seats?: string[];
  unknown_items?: string[];
  unavailable_items?: string[];
  limit?: number;
  already_held?: string[];
  [key: string]: unknown;
};

export class ApiError extends Error {
  readonly status: number;
  readonly details?: ApiErrorDetails;

  constructor(status: number, message: string, details?: ApiErrorDetails) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }

  /** Seats lost to another user, when the failure was a lock conflict. */
  get conflicts(): string[] {
    return this.details?.conflicts ?? [];
  }
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  token?: string | null;
  headers?: Record<string, string>;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, token, headers = {} } = options;

  const response = await fetch(`${V1}${path}`, {
    method,
    // Deliberately not `credentials: "include"`. The API answers with
    // `Allow-Origin: *` alongside `Allow-Credentials: true`, a combination
    // browsers reject for credentialed requests. Auth is a bearer header, so
    // the default omit is both correct and what works.
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }

  if (!response.ok) {
    const error = payload as { message?: string; details?: ApiErrorDetails };
    throw new ApiError(
      response.status,
      error.message ?? `Request failed with ${response.status}`,
      error.details,
    );
  }

  return (payload as Envelope<T>).data;
}

// --- auth -----------------------------------------------------------------

export const api = {
  issueToken: (name: string) =>
    request<TokenResponse>("/auth/token", { method: "POST", body: { name } }),

  // --- catalogue ----------------------------------------------------------

  listMovies: (params: { q?: string; section?: MovieSection; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.q) query.set("q", params.q);
    if (params.section) query.set("section", params.section);
    if (params.limit) query.set("limit", String(params.limit));
    const suffix = query.toString();
    return request<Paged<MovieSummary>>(`/movies${suffix ? `?${suffix}` : ""}`);
  },

  getMovie: (movieId: string) => request<MovieDetail>(`/movies/${movieId}`),

  listReviews: (movieId: string) =>
    request<ReviewList>(`/movies/${movieId}/reviews`),

  // --- venues -------------------------------------------------------------

  listLocations: () => request<Location[]>("/locations"),

  listCinemas: (locationId?: string) =>
    request<CinemaSummary[]>(
      `/cinemas${locationId ? `?location_id=${encodeURIComponent(locationId)}` : ""}`,
    ),

  listShowtimes: (params: { movieId: string; cinemaId?: string; date?: string }) => {
    const query = new URLSearchParams({ movie_id: params.movieId });
    if (params.cinemaId) query.set("cinema_id", params.cinemaId);
    if (params.date) query.set("date", params.date);
    return request<ShowtimeSummary[]>(`/showtimes?${query}`);
  },

  // --- seats --------------------------------------------------------------

  getSeatPlan: (showtimeId: string, token?: string | null) =>
    request<SeatPlan>(`/showtimes/${showtimeId}/seats`, { token }),

  getSeatChanges: (showtimeId: string, since: string, token?: string | null) =>
    request<SeatChangeList>(
      `/showtimes/${showtimeId}/seats/changes?since=${encodeURIComponent(since)}`,
      { token },
    ),

  lockSeats: (showtimeId: string, seats: string[], token: string) =>
    request<LockResult>(`/showtimes/${showtimeId}/seats/lock`, {
      method: "POST",
      body: { seats },
      token,
    }),

  releaseSeats: (showtimeId: string, seats: string[], token: string) =>
    request<ReleaseResult>(`/showtimes/${showtimeId}/seats/lock`, {
      method: "DELETE",
      body: { seats },
      token,
    }),

  heartbeat: (showtimeId: string, seats: string[], token: string) =>
    request<LockResult>(`/showtimes/${showtimeId}/seats/lock/heartbeat`, {
      method: "POST",
      body: { seats },
      token,
    }),

  // --- food and beverage --------------------------------------------------

  listFnb: (category?: FnbCategory) =>
    request<FnbItem[]>(`/fnb${category ? `?category=${category}` : ""}`),

  // --- bookings -----------------------------------------------------------

  createBooking: (showtimeId: string, seats: string[], token: string) =>
    request<Booking>("/bookings", {
      method: "POST",
      body: { showtime_id: showtimeId, seats },
      token,
    }),

  getBooking: (bookingId: string, token: string) =>
    request<Booking>(`/bookings/${bookingId}`, { token }),

  setFnb: (
    bookingId: string,
    items: { fnb_id: string; quantity: number }[],
    token: string,
  ) =>
    request<Booking>(`/bookings/${bookingId}/fnb`, {
      method: "PUT",
      body: { items },
      token,
    }),

  cancelBooking: (bookingId: string, token: string) =>
    request<Booking>(`/bookings/${bookingId}`, { method: "DELETE", token }),

  // --- payment ------------------------------------------------------------

  listPaymentMethods: () => request<PaymentMethodOption[]>("/payment-methods"),

  pay: (
    bookingId: string,
    body: {
      method: PaymentMethod;
      card?: { number: string; expiry: string; cvv: string };
    },
    token: string,
    idempotencyKey: string,
  ) =>
    request<Booking>(`/bookings/${bookingId}/pay`, {
      method: "POST",
      body,
      token,
      // Retrying with the same key returns the original charge rather than
      // billing twice.
      headers: { "Idempotency-Key": idempotencyKey },
    }),

  getTicket: (bookingId: string, token: string) =>
    request<Ticket>(`/bookings/${bookingId}/ticket`, { token }),
};

/** WebSocket URL for a screening's live seat changes. */
export function seatSocketUrl(showtimeId: string, token?: string | null): string {
  const base = API_BASE.replace(/^http/, "ws");
  const suffix = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${base}/api/v1/ws/showtimes/${showtimeId}${suffix}`;
}
