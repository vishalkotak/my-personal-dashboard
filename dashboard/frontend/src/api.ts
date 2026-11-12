import { useEffect, useState } from "react";
import type { DateRange } from "./lib/range";

// ---------------------------------------------------------------- response types

export interface Health {
  ok: boolean;
  demo: boolean;
  database_reachable: boolean;
  last_upload: string | null;
  tz: string;
}

export interface SparkPoint {
  date: string;
  value: number | null;
}

export interface NightData {
  night: string;
  has_data: boolean;
  asleep_min?: number;
  deep_min?: number;
  core_min?: number;
  rem_min?: number;
  unspecified_min?: number;
  awake_min?: number;
  in_bed_min?: number;
  staged?: boolean;
  start?: string | null;
  end?: string | null;
}

export interface Summary {
  today: string;
  days: number;
  cards: {
    steps: { today: number | null; average: number | null; unit: string; spark: SparkPoint[] };
    active_energy: { today: number | null; average: number | null; unit: string; spark: SparkPoint[] };
    resting_hr: { latest: number | null; latest_date: string | null; average: number | null; unit: string; spark: SparkPoint[] };
    hrv: { latest: number | null; latest_date: string | null; average: number | null; unit: string; spark: SparkPoint[] };
    sleep: { last_night: NightData | null; average: number | null; spark: SparkPoint[] };
    weight: { latest: number | null; latest_date: string | null; average: number | null; unit: string; spark: SparkPoint[] };
  };
}

export interface CumulativePoint {
  date: string;
  value: number | null;
  raw_sum: number | null;
}
export interface DiscretePoint {
  date: string;
  avg: number | null;
  min: number | null;
  max: number | null;
  last?: number | null;
  count: number;
}
export interface Daily<P> {
  type: string;
  kind: "cumulative" | "discrete";
  unit: string;
  approximate: boolean;
  note?: string;
  points: P[];
}

export interface HeartDay {
  date: string;
  hr_min: number | null;
  hr_avg: number | null;
  hr_max: number | null;
  resting: number | null;
  hrv: number | null;
}

export interface BodyData {
  days: { date: string; weight: number | null; spo2_avg: number | null; spo2_min: number | null; temp: number | null }[];
  blood_pressure: { time: string; date: string; systolic: number; diastolic: number }[];
  unpaired_bp_readings: number;
}

export interface Workout {
  start: string;
  end: string;
  date: string;
  duration_min: number;
  activity_type: number | null;
  name: string;
}
export interface WorkoutsData {
  workouts: Workout[];
  weekly: { week_start: string; minutes: number; count: number }[];
  by_type: { name: string; count: number; minutes: number }[];
}

export interface TypeEntry {
  id: string;
  kind: "quantity" | "category" | "workout";
  group: string;
  name: string;
  unit: string | null;
  aggregation: "sum" | "average" | "duration";
  display_unit: string;
  count: number;
  latest: string | null;
}
export interface TypesData {
  catalog_source: "file" | "builtin";
  catalog_size: number;
  types: TypeEntry[];
}

export interface DurationPoint {
  date: string;
  minutes: number | null;
  count: number;
  breakdown: Record<string, number>;
}
export type MetricData =
  | { aggregation: "sum"; type: TypeEntry; display_unit: string; approximate: true; note: string; points: CumulativePoint[] }
  | { aggregation: "average"; type: TypeEntry; display_unit: string; points: DiscretePoint[] }
  | {
      aggregation: "duration";
      type: TypeEntry;
      display_unit: "min";
      labels: string[];
      per: "day" | "night";
      points: DurationPoint[];
    };

// ---------------------------------------------------------------- fetching

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal, headers: { Accept: "application/json" }, credentials: "omit" });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export function rangeQuery(range: DateRange, extra: Record<string, string> = {}): string {
  return new URLSearchParams({ from: range.from, to: range.to, ...extra }).toString();
}

export interface Loadable<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** Fetch `path` whenever it changes; cancels stale requests. */
export function useApi<T>(path: string | null): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ data: null, error: null, loading: !!path });
  useEffect(() => {
    if (!path) return;
    const ctrl = new AbortController();
    setState((s) => ({ data: s.data, error: null, loading: true }));
    getJSON<T>(path, ctrl.signal)
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        const msg =
          e instanceof ApiError
            ? e.message
            : "Can't reach the dashboard backend. Is it running? (./dashboard/start.sh)";
        setState({ data: null, error: msg, loading: false });
      });
    return () => ctrl.abort();
  }, [path]);
  return state;
}
