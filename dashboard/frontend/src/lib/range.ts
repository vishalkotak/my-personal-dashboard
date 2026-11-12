// Date ranges. Everything is a local calendar date in YYYY-MM-DD form, inclusive at both ends.

export type Preset = "7d" | "30d" | "90d" | "1y" | "custom";
export const PRESETS: { id: Preset; label: string; days: number }[] = [
  { id: "7d", label: "7D", days: 7 },
  { id: "30d", label: "30D", days: 30 },
  { id: "90d", label: "90D", days: 90 },
  { id: "1y", label: "1Y", days: 365 },
];

/** Matches the backend's cap (3 × 366 days). */
export const MAX_RANGE_DAYS = 3 * 366;

export interface DateRange {
  preset: Preset;
  from: string;
  to: string;
}

const ISO = /^\d{4}-\d{2}-\d{2}$/;

export function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Parse YYYY-MM-DD as a local date at noon (noon dodges DST edge cases). */
export function parseISODate(s: string): Date | null {
  if (!ISO.test(s)) return null;
  const [y, m, d] = s.split("-").map(Number);
  const date = new Date(y, m - 1, d, 12);
  return date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d ? date : null;
}

export function addDays(iso: string, n: number): string {
  const d = parseISODate(iso);
  if (!d) throw new Error(`bad date ${iso}`);
  d.setDate(d.getDate() + n);
  return toISODate(d);
}

/** Number of days from `from` to `to`, inclusive. */
export function daysInclusive(from: string, to: string): number {
  const a = parseISODate(from);
  const b = parseISODate(to);
  if (!a || !b) return NaN;
  return Math.round((b.getTime() - a.getTime()) / 86_400_000) + 1;
}

export function presetRange(preset: Exclude<Preset, "custom">, today: string): DateRange {
  const days = PRESETS.find((p) => p.id === preset)!.days;
  return { preset, from: addDays(today, -(days - 1)), to: today };
}

/** Returns an error message, or null if the custom range is usable. */
export function validateRange(from: string, to: string, today: string): string | null {
  if (!parseISODate(from) || !parseISODate(to)) return "Pick both dates.";
  if (from > to) return "The start date is after the end date.";
  if (to > today) return "The end date is in the future.";
  if (from < "2000-01-01") return "Dates before 2000 aren't supported.";
  if (daysInclusive(from, to) > MAX_RANGE_DAYS) return "Ranges are limited to 3 years.";
  return null;
}

/** Read a range from URL search params, falling back to 30 days. */
export function rangeFromParams(params: URLSearchParams, today: string): DateRange {
  const r = params.get("range");
  if (r === "custom") {
    const from = params.get("from") ?? "";
    const to = params.get("to") ?? "";
    if (!validateRange(from, to, today)) return { preset: "custom", from, to };
  } else if (PRESETS.some((p) => p.id === r)) {
    return presetRange(r as Exclude<Preset, "custom">, today);
  }
  return presetRange("30d", today);
}

export function rangeToParams(range: DateRange): Record<string, string> {
  return range.preset === "custom"
    ? { range: "custom", from: range.from, to: range.to }
    : { range: range.preset };
}
