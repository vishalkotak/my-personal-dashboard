// Number, unit, duration and date formatting. Pure functions, unit-tested.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const DASH = "—";

/** Thousands separators, a sensible number of decimals for the magnitude. */
export function formatNumber(v: number | null | undefined, decimals?: number): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return DASH;
  const abs = Math.abs(v);
  const d = decimals ?? (abs >= 100 ? 0 : abs >= 10 ? 1 : abs >= 1 ? 1 : abs === 0 ? 0 : 2);
  return v.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: d });
}

/** Grams auto-scale to mg / µg for small values (nutrition is stored in grams). */
export function scaleMass(grams: number): { value: number; unit: string } {
  const abs = Math.abs(grams);
  if (abs !== 0 && abs < 0.001) return { value: grams * 1_000_000, unit: "µg" };
  if (abs !== 0 && abs < 1) return { value: grams * 1000, unit: "mg" };
  return { value: grams, unit: "g" };
}

/**
 * Format a value in its display unit. The backend has already applied the "%" ×100
 * conversion and turned count/min into bpm; this handles the per-value parts.
 */
export function formatValue(v: number | null | undefined, unit: string, decimals?: number): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return DASH;
  if (unit === "g") {
    const s = scaleMass(v);
    return `${formatNumber(s.value, decimals)} ${s.unit}`;
  }
  if (unit === "m" && Math.abs(v) >= 1000) return `${formatNumber(v / 1000, decimals ?? 2)} km`;
  if (unit === "min") return formatMinutes(v);
  if (unit === "%") return `${formatNumber(v, decimals ?? 1)}%`;
  if (unit === "" || unit === "count" || unit === "steps") return formatNumber(v, decimals ?? (Math.abs(v) >= 10 ? 0 : 1));
  return `${formatNumber(v, decimals)} ${unit}`;
}

/** 452 -> "7h 32m", 45 -> "45m", 0.5 -> "30s". */
export function formatMinutes(min: number | null | undefined): string {
  if (min === null || min === undefined || !Number.isFinite(min)) return DASH;
  if (min > 0 && min < 1) return `${Math.round(min * 60)}s`;
  const total = Math.round(min);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m}m`;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

/** Minutes -> hours with one decimal, for chart axes. */
export function minutesToHours(min: number | null | undefined): number | null {
  return min === null || min === undefined ? null : Math.round((min / 60) * 10) / 10;
}

/** "2026-11-03" -> "Nov 3"; with year -> "Nov 3, 2026". */
export function formatDate(iso: string, withYear = false): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return withYear ? `${MONTHS[m - 1]} ${d}, ${y}` : `${MONTHS[m - 1]} ${d}`;
}

/** Local clock time of an ISO instant, e.g. "11:04 PM". */
export function formatTime(isoInstant: string): string {
  const d = new Date(isoInstant);
  if (Number.isNaN(d.getTime())) return DASH;
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

/** "3 days ago", "today" — for "last synced" style labels. */
export function formatAgo(isoInstant: string | null | undefined, now: Date = new Date()): string {
  if (!isoInstant) return "never";
  const t = new Date(isoInstant).getTime();
  if (Number.isNaN(t)) return DASH;
  const mins = Math.round((now.getTime() - t) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

export function average(values: (number | null | undefined)[]): number | null {
  const v = values.filter((x): x is number => typeof x === "number" && Number.isFinite(x));
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

/** Tick interval so a time axis shows roughly `target` labels. */
export function tickInterval(points: number, target = 7): number {
  return Math.max(0, Math.ceil(points / target) - 1);
}
