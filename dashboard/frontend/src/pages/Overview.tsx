import { useApi, type SparkPoint, type Summary } from "../api";
import { C, Sparkline } from "../components/charts";
import { ErrorState, EmptyState } from "../components/ui";
import { DASH, formatDate, formatMinutes, formatNumber, formatValue } from "../lib/format";
import type { Tab } from "../tabs";

function OverviewCard({
  title,
  value,
  unit,
  detail,
  spark,
  color,
  kind,
  tab,
  onOpen,
  badge,
}: {
  title: string;
  value: string;
  unit?: string;
  detail: string;
  spark: SparkPoint[];
  color: string;
  kind?: "line" | "bar";
  tab: Tab;
  onOpen: (t: Tab) => void;
  badge?: string;
}) {
  return (
    <button type="button" className="ov-card" onClick={() => onOpen(tab)} aria-label={`${title}: ${value} ${unit ?? ""}. Open ${tab}`}>
      <div className="ov-head">
        <span className="ov-title">
          <span className="dot" style={{ background: color }} />
          {title}
        </span>
        {badge && (
          <span className="badge" title="iPhone and Apple Watch samples can overlap; this total is de-duplicated by estimate.">
            {badge}
          </span>
        )}
      </div>
      <div className="ov-value">
        {value}
        {unit && value !== DASH && <span className="ov-unit">{unit}</span>}
      </div>
      <div className="ov-detail">{detail}</div>
      <Sparkline points={spark} color={color} kind={kind} />
    </button>
  );
}

export function Overview({ onOpen }: { onOpen: (t: Tab) => void }) {
  const s = useApi<Summary>("/api/summary?days=7");
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
  const nothing =
    c.steps.spark.every((p) => p.value == null) &&
    c.resting_hr.latest == null &&
    c.sleep.last_night == null &&
    c.weight.latest == null;
  const last = c.sleep.last_night;
  const avg7 = (v: number | null, unit: string) => (v == null ? "No 7-day average yet" : `7-day avg ${formatValue(v, unit)}`);

  return (
    <>
      {nothing && <EmptyState />}
      <div className="ov-grid">
        <OverviewCard
          title="Steps today"
          value={formatNumber(c.steps.today, 0)}
          detail={avg7(c.steps.average, "steps")}
          spark={c.steps.spark}
          color={C.blue}
          kind="bar"
          tab="activity"
          onOpen={onOpen}
          badge="≈ approx."
        />
        <OverviewCard
          title="Active energy"
          value={formatNumber(c.active_energy.today, 0)}
          unit="kcal"
          detail={avg7(c.active_energy.average, "kcal")}
          spark={c.active_energy.spark}
          color={C.orange}
          kind="bar"
          tab="activity"
          onOpen={onOpen}
          badge="≈ approx."
        />
        <OverviewCard
          title="Resting heart rate"
          value={formatNumber(c.resting_hr.latest, 0)}
          unit="bpm"
          detail={`${c.resting_hr.latest_date ? formatDate(c.resting_hr.latest_date) + " · " : ""}${avg7(c.resting_hr.average, "bpm")}`}
          spark={c.resting_hr.spark}
          color={C.red}
          tab="heart"
          onOpen={onOpen}
        />
        <OverviewCard
          title="Heart rate variability"
          value={formatNumber(c.hrv.latest, 0)}
          unit="ms"
          detail={`${c.hrv.latest_date ? formatDate(c.hrv.latest_date) + " · " : ""}${avg7(c.hrv.average, "ms")}`}
          spark={c.hrv.spark}
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
                ? `Deep ${formatMinutes(last.deep_min)} · REM ${formatMinutes(last.rem_min)} · ${formatDate(last.night)}`
                : `No stage data · ${formatDate(last.night)}`
              : "No sleep recorded yet"
          }
          spark={c.sleep.spark.map((p) => ({ ...p, value: p.value == null ? null : p.value / 60 }))}
          color={C.core}
          kind="bar"
          tab="sleep"
          onOpen={onOpen}
        />
        <OverviewCard
          title="Weight"
          value={formatNumber(c.weight.latest, 1)}
          unit="kg"
          detail={c.weight.latest_date ? `Weighed ${formatDate(c.weight.latest_date, true)}` : "No weigh-ins yet"}
          spark={c.weight.spark}
          color={C.aqua}
          tab="body"
          onOpen={onOpen}
        />
      </div>
      <p className="footnote">
        Sparklines show the last 30 days. Step and energy totals are approximate: the iPhone and Apple Watch both
        record them and their samples are de-duplicated by estimate.
      </p>
    </>
  );
}
