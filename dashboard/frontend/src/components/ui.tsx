import { useState, type ReactNode } from "react";
import type { Loadable } from "../api";
import { PRESETS, presetRange, validateRange, type DateRange } from "../lib/range";

export const EMPTY_MESSAGE = "No data yet — open the HealthSync app on your iPhone.";

export function Card({
  title,
  subtitle,
  children,
  wide,
  aside,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  wide?: boolean;
  aside?: ReactNode;
}) {
  return (
    <section className={`card${wide ? " card-wide" : ""}`}>
      <header className="card-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="card-sub">{subtitle}</p>}
        </div>
        {aside}
      </header>
      {children}
    </section>
  );
}

export function EmptyState({ message = EMPTY_MESSAGE, compact }: { message?: string; compact?: boolean }) {
  return (
    <div className={`empty${compact ? " empty-compact" : ""}`} role="status">
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <path
          d="M12 21s-7-4.4-9.3-9A5.2 5.2 0 0 1 12 6.6 5.2 5.2 0 0 1 21.3 12C19 16.6 12 21 12 21z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
      </svg>
      <span>{message}</span>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="empty error" role="alert">
      <strong>Couldn't load this.</strong> <span>{message}</span>
    </div>
  );
}

/** Renders loading / error / empty states, or the children with data. */
export function Load<T>({
  state,
  isEmpty,
  children,
  height = 240,
}: {
  state: Loadable<T>;
  isEmpty?: (data: T) => boolean;
  children: (data: T) => ReactNode;
  height?: number;
}) {
  if (state.error) return <ErrorState message={state.error} />;
  if (!state.data) return <div className="skeleton" style={{ height }} aria-busy="true" aria-label="Loading" />;
  if (isEmpty?.(state.data)) return <EmptyState />;
  return <div className={state.loading ? "refreshing" : undefined}>{children(state.data)}</div>;
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="notice" role="note">
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <path d="M12 11v6M12 7.5v.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      <span>{children}</span>
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <ul className="legend" aria-label="Legend">
      {items.map((i) => (
        <li key={i.label}>
          <span
            className={`swatch${i.dashed ? " swatch-line" : ""}`}
            style={i.dashed ? { borderColor: i.color } : { background: i.color }}
          />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

export function RangePicker({
  range,
  today,
  onChange,
}: {
  range: DateRange;
  today: string;
  onChange: (r: DateRange) => void;
}) {
  const [custom, setCustom] = useState(range.preset === "custom");
  const [from, setFrom] = useState(range.from);
  const [to, setTo] = useState(range.to);
  const error = custom ? validateRange(from, to, today) : null;

  return (
    <div className="range">
      <div className="segmented" role="group" aria-label="Date range">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            aria-pressed={!custom && range.preset === p.id}
            onClick={() => {
              setCustom(false);
              onChange(presetRange(p.id as Exclude<typeof p.id, "custom">, today));
            }}
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={custom}
          onClick={() => {
            setCustom(true);
            setFrom(range.from);
            setTo(range.to);
          }}
        >
          Custom
        </button>
      </div>
      {custom && (
        <form
          className="custom-range"
          onSubmit={(e) => {
            e.preventDefault();
            if (!error) onChange({ preset: "custom", from, to });
          }}
        >
          <label>
            <span className="sr-only">From</span>
            <input type="date" value={from} max={today} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <span aria-hidden="true">–</span>
          <label>
            <span className="sr-only">To</span>
            <input type="date" value={to} max={today} onChange={(e) => setTo(e.target.value)} />
          </label>
          <button type="submit" disabled={!!error}>
            Apply
          </button>
          {error && <span className="range-error">{error}</span>}
        </form>
      )}
    </div>
  );
}
