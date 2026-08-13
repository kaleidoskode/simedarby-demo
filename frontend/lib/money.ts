/**
 * Formatting for amounts the server has not priced yet.
 *
 * Every authoritative amount arrives from the API as a `Money` with a
 * preformatted `display` string, and that string should always be rendered
 * as-is. This exists only for the two live previews shown *before* a booking
 * exists, where there is nothing to ask the server for:
 *
 *   - the seat sub-total while the user is still choosing seats
 *   - the food sub-total while quantities are being adjusted
 *
 * Both are replaced by server-computed amounts the moment the booking is
 * created, so a discrepancy here can never reach a total that is charged.
 *
 * The symbol table mirrors the server's, and the currency comes from the API
 * rather than being assumed, so a screening priced in another currency
 * previews correctly instead of claiming ringgit.
 */

const SYMBOLS: Record<string, string> = {
  MYR: "RM",
  SGD: "S$",
  USD: "$",
  GBP: "£",
  EUR: "€",
  NGN: "₦",
  JPY: "¥",
};

/** Currencies whose smallest unit is the unit itself, so they take no decimals. */
const ZERO_DECIMAL = new Set(["JPY", "KRW", "VND", "IDR"]);

export function formatMinor(minor: number, currency = "MYR"): string {
  const symbol = SYMBOLS[currency] ?? `${currency} `;

  if (ZERO_DECIMAL.has(currency)) {
    return `${symbol}${minor.toLocaleString("en-US")}`;
  }

  const major = Math.floor(Math.abs(minor) / 100);
  const remainder = Math.abs(minor) % 100;
  const sign = minor < 0 ? "-" : "";

  return `${sign}${symbol}${major.toLocaleString("en-US")}.${String(remainder).padStart(2, "0")}`;
}
