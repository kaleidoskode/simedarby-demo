/**
 * Mirrors the Cinema Booking API schemas.
 *
 * Hand-written rather than generated: the surface is small, and keeping it here
 * means the demo documents the contract it depends on. The source of truth is
 * the OpenAPI schema at /openapi.json.
 */

export type Money = {
  minor: number;
  currency: string;
  /** Preformatted for display, e.g. "RM25.00". Never format money client side. */
  display: string;
};

export type Envelope<T> = {
  success: boolean;
  message: string;
  data: T;
};

export type PageMeta = {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
};

export type Paged<T> = {
  items: T[];
  meta: PageMeta;
};

// --- auth -----------------------------------------------------------------

export type CurrentUser = {
  id: string;
  name: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: CurrentUser;
};

// --- catalogue ------------------------------------------------------------

export type MovieSection = "new_release" | "popular" | "recommended";

export type MovieSummary = {
  id: string;
  title: string;
  poster_url: string | null;
  genres: string[];
  duration_mins: number;
  certification: string;
  rating_avg: number;
  rating_count: number;
  sections: MovieSection[];
};

export type MovieDetail = MovieSummary & {
  synopsis: string;
  trailer_url: string | null;
  release_date: string;
  casts: string[];
  director: string | null;
  writers: string[];
  formats: string[];
};

export type Review = {
  id: string;
  movie_id: string;
  author: string;
  stars: number;
  title: string;
  body: string;
  created_at: string;
};

export type ReviewList = {
  breakdown: {
    average: number;
    total: number;
    /** Keyed by star value; JSON object keys arrive as strings. */
    counts: Record<string, number>;
  };
  items: Review[];
  meta: PageMeta;
};

// --- venues ---------------------------------------------------------------

export type Location = {
  id: string;
  name: string;
  country: string;
};

export type CinemaSummary = {
  id: string;
  name: string;
  location_id: string;
  location_name: string;
  price_from: Money;
  price_to: Money;
};

export type ShowtimeSummary = {
  id: string;
  movie_id: string;
  cinema_id: string;
  cinema_name: string;
  hall_id: string;
  starts_at: string;
  ends_at: string;
  display_time: string;
  price: Money;
  ticket_class: string;
  format: string | null;
  language: string | null;
};

// --- seats ----------------------------------------------------------------

export type SeatStatus = "available" | "locked" | "booked";

export type SeatState = {
  seat: string;
  row: string;
  number: number;
  status: SeatStatus;
  /** Distinguishes the caller's own hold (Selected) from someone else's. */
  held_by_me: boolean;
};

export type SeatPlanRow = {
  row: string;
  seats: SeatState[];
};

export type SeatPlan = {
  showtime_id: string;
  hall_id: string;
  hall_name: string;
  price: Money;
  rows: SeatPlanRow[];
  summary: { total: number; available: number; locked: number; booked: number };
  /** Position in the change log. Pass back as ?since= to catch up. */
  version: string;
};

export type SeatChange = {
  seat: string;
  status: SeatStatus;
  held_by_me: boolean;
  at: string;
};

export type SeatChangeList = {
  showtime_id: string;
  version: string;
  changes: SeatChange[];
};

export type LockResult = {
  showtime_id: string;
  seats: string[];
  holder: string;
  ttl_seconds: number;
  expires_at: string;
};

export type ReleaseResult = {
  showtime_id: string;
  released: string[];
  ignored: string[];
};

/** Pushed over the WebSocket. */
export type RealtimeMessage =
  | { type: "snapshot"; version: string; plan: SeatPlan }
  | { type: "seat_change"; version: string; changes: SeatChange[] };

// --- food and beverage ----------------------------------------------------

export type FnbCategory = "combo" | "food_snacks" | "beverages";

export type FnbItem = {
  id: string;
  category: FnbCategory;
  name: string;
  description: string;
  image_url: string | null;
  price: Money;
  original_price: Money | null;
  discount_pct: number | null;
  is_available: boolean;
};

// --- bookings -------------------------------------------------------------

export type BookingStatus =
  | "draft"
  | "awaiting_payment"
  | "confirmed"
  | "cancelled"
  | "expired";

export type FnbLine = {
  fnb_id: string;
  name: string;
  unit_price: Money;
  quantity: number;
  line_total: Money;
};

export type BookingScreening = {
  showtime_id: string;
  movie_title: string;
  genres: string[];
  duration_mins: number;
  formats: string[];
  poster_url: string | null;
  cinema_name: string;
  hall_name: string;
  display_date: string;
  starts_at: string;
  ends_at: string;
  start_display: string;
  end_display: string;
};

export type Booking = {
  id: string;
  reference: string;
  user_id: string;
  showtime_id: string;
  screening: BookingScreening;
  seats: string[];
  status: BookingStatus;
  ticket_class: string;
  fnb_items: FnbLine[];
  amounts: {
    tickets: Money;
    fnb: Money;
    service_charge: Money;
    total: Money;
  };
  payment: {
    method: PaymentMethod | null;
    status: "pending" | "succeeded" | "failed";
    reference: string | null;
    card_last4: string | null;
    paid_at: string | null;
  };
  created_at: string;
  expires_at: string | null;
  confirmed_at: string | null;
};

// --- payment --------------------------------------------------------------

export type PaymentMethod = "debit_card" | "bank_transfer" | "crypto_wallet";

export type PaymentMethodOption = {
  id: PaymentMethod;
  label: string;
  description: string;
  requires_card: boolean;
};

export type Ticket = {
  reference: string;
  movie_title: string;
  poster_url: string | null;
  cinema_name: string;
  hall_name: string;
  seats: string[];
  ticket_class: string;
  display_date: string;
  start_display: string;
  end_display: string;
  starts_at: string;
  total_paid: Money;
  issued_at: string;
  qr_payload: string;
};
