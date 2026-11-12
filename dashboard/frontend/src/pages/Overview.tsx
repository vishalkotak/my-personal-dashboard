import { useApi, type Summary } from "../api";
import { C } from "../components/charts";
import { ErrorState, EmptyState } from "../components/ui";
import { DASH, formatDate, formatMinutes, formatNumber, formatValue } from "../lib/format";
import type { Tab } from "../tabs";

function OverviewCard({
  title,
  value,
  unit,
  detail,
  color,
  tab,
  onOpen,
}: {
  title: string;
  value: string;
  unit?: string;
  detail: string;
  color: string;
  tab: Tab;
  onOpen: (t: Tab) => void;
}) {
  return (
    <button type="button" className="ov-card" onClick={() => onOpen(tab)} aria-label={`${title}: ${value} ${unit ?? ""}. Open ${tab}`}>
      <div className="ov-head">
        <span className="ov-title">
          <span className="dot" style={{ background: color }} />
          {title}
        </span>
      </div>
      <div className="ov-value">
        {value}
        {unit && value !== DASH && <span className="ov-unit">{unit}</span>}
      </div>
      <div className="ov-detail">{detail}</div>
    </button>
  );
}

export function Overview({ onOpen }: { onOpen: (t: Tab) => void }) {
  const s = useApi<Summary>("/api/summary?days=1");
  if (s.error) return <ErrorState message={s.error} />;
  if (!s.data)
    return (
      <div className="ov-grid">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="skeleton ov-skeleton" aria-busy="true" />
        ))}
      </div>
    );

  const c = s.data.cards;
  const today = s.data.today;
  const nothing =
    c.steps.spark.every((p) => p.value == null) &&
    c.resting_hr.latest == null &&
    c.sleep.last_night == null &&
    c.weight.latest == null;

  // Today only: a reading from an earlier day shows as "—", with when it was last seen.
  const todays = (v: number | null, d: string | null) => (d === today ? v : null);
  const when = (d: string) => formatDate(d, d.slice(0, 4) !== today.slice(0, 4)); // year only if not this year
  const notToday = (v: number | null, d: string | null, unit: string, verb = "Last reading") =>
    v == null || d == null ? "No readings yet" : `None today · ${verb.toLowerCase()} ${formatValue(v, unit)} on ${when(d)}`;
  const sleepNight = c.sleep.last_night;
  const last = sleepNight?.night === today ? sleepNight : null;

  return (
    <>
      {nothing && <EmptyState />}
      <div className="ov-grid">
        <OverviewCard
          title="Steps"
          value={formatNumber(c.steps.today, 0)}
          detail="So far today"
          color={C.blue}
          tab="activity"
          onOpen={onOpen}
        />
        <OverviewCard
          title="Active energy"
          value={formatNumber(c.active_energy.today, 0)}
          unit="kcal"
          detail={c.active_energy.today == null ? "Nothing recorded today" : "So far today"}
          color={C.orange}
          tab="activity"
          onOpen={onOpen}
        />
        <OverviewCard
          title="Resting heart rate"
          value={formatNumber(todays(c.resting_hr.latest, c.resting_hr.latest_date), 0)}
          unit="bpm"
          detail={
            c.resting_hr.latest_date === today
              ? "Today"
              : notToday(c.resting_hr.latest, c.resting_hr.latest_date, "bpm")
          }
          color={C.red}
          tab="heart"
          onOpen={onOpen}
        />
        <OverviewCard
          title="Heart rate variability"
          value={formatNumber(todays(c.hrv.latest, c.hrv.latest_date), 0)}
          unit="ms"
          detail={c.hrv.latest_date === today ? "Today" : notToday(c.hrv.latest, c.hrv.latest_date, "ms")}
          color={C.violet}
          tab="heart"
          onOpen={onOpen}
        />
        <OverviewCard
          title="Last night's sleep"
          value={last ? formatMinutes(last.asleep_min) : DASH}
          detail={
            last
              ? last.staged
                ? `Deep ${formatMinutes(last.deep_min)} · REM ${formatMinutes(last.rem_min)}`
                : "No stage data"
              : sleepNight
                ? `Not recorded last night · last on ${when(sleepNight.night)}`
                : "No sleep recorded yet"
          }
          color={C.core}
          tab="sleep"
          onOpen={onOpen}
        />
        <OverviewCard
          title="Weight"
          value={formatNumber(todays(c.weight.latest, c.weight.latest_date), 1)}
          unit="kg"
          detail={
            c.weight.latest_date === today
              ? "Weighed today"
              : notToday(c.weight.latest, c.weight.latest_date, "kg", "Last weighed")
          }
          color={C.aqua}
          tab="body"
          onOpen={onOpen}
        />
      </div>
    </>
  );
}
