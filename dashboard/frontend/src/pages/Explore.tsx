import { useMemo, useState } from "react";
import { rangeQuery, useApi, type MetricData, type TypeEntry, type TypesData } from "../api";
import { C, DailyBars, StackedBars, TableToggle, TrendLines } from "../components/charts";
import { Card, EmptyState, ErrorState, Legend, Load, Stat } from "../components/ui";
import { average, formatAgo, formatDate, formatNumber, formatValue } from "../lib/format";
import type { DateRange } from "../lib/range";
import { groupTypes } from "../lib/explore";

// Fixed categorical order for category breakdowns (never cycled past the end).
const BREAKDOWN_COLORS = [C.blue, C.orange, C.aqua, C.yellow, C.magenta, C.violet, C.red];

function MetricView({ entry, range }: { entry: TypeEntry; range: DateRange }) {
  const state = useApi<MetricData>(`/api/metric?${rangeQuery(range, { type: entry.id })}`);
  return (
    <Card title={entry.name} subtitle={<code className="type-id">{entry.id}</code>} wide>
      <Load
        state={state}
        isEmpty={(m) =>
          m.aggregation === "sum"
            ? m.points.every((p) => p.value == null)
            : m.aggregation === "average"
              ? m.points.every((p) => p.avg == null)
              : m.points.every((p) => p.minutes == null)
        }
      >
        {(m) => <MetricBody m={m} />}
      </Load>
    </Card>
  );
}

function MetricBody({ m }: { m: MetricData }) {
  const unit = m.display_unit;
  if (m.aggregation === "sum") {
    const vals = m.points.map((p) => p.value);
    return (
      <>
        <div className="stats">
          <Stat label="Daily average" value={formatValue(average(vals), unit)} />
          <Stat label="Total" value={formatValue(vals.reduce<number>((a, v) => a + (v ?? 0), 0), unit)} />
          <Stat label="Days with data" value={String(vals.filter((v) => v != null).length)} />
        </div>
        <DailyBars
          data={m.points as never}
          dataKey="value"
          color={C.blue}
          unit={unit}
          label="Total"
          average={average(vals)}
        />
        <PointsTable rows={m.points.map((p) => [p.date, formatValue(p.value, unit)])} head={["Total"]} />
      </>
    );
  }
  if (m.aggregation === "average") {
    const vals = m.points.map((p) => p.avg);
    const n = m.points.reduce((a, p) => a + p.count, 0);
    return (
      <>
        <div className="stats">
          <Stat label="Average" value={formatValue(average(vals), unit)} />
          <Stat label="Lowest" value={formatValue(Math.min(...m.points.map((p) => p.min ?? Infinity)), unit)} />
          <Stat label="Highest" value={formatValue(Math.max(...m.points.map((p) => p.max ?? -Infinity)), unit)} />
          <Stat label="Readings" value={formatNumber(n, 0)} />
        </div>
        <TrendLines
          data={m.points as never}
          lines={[{ key: "avg", label: "Daily average", color: C.blue }]}
          band={{ min: "min", max: "max", label: "Range" }}
          unit={unit}
        />
        <PointsTable
          rows={m.points.map((p) => [p.date, formatValue(p.avg, unit), formatValue(p.min, unit), formatValue(p.max, unit), String(p.count)])}
          head={["Average", "Min", "Max", "Readings"]}
        />
      </>
    );
  }
  // duration (categories and workouts)
  const labels = m.labels.slice(0, BREAKDOWN_COLORS.length);
  const series = labels.map((l, i) => ({ key: `bd_${i}`, label: l, color: BREAKDOWN_COLORS[i] }));
  const rows = m.points.map((p) => {
    const o: Record<string, unknown> = { ...p };
    labels.forEach((l, i) => (o[`bd_${i}`] = p.breakdown[l] ?? null));
    return o;
  });
  const minutes = m.points.map((p) => p.minutes);
  const events = m.points.reduce((a, p) => a + p.count, 0);
  const isPointEvents = minutes.every((v) => v == null || v === 0);
  return (
    <>
      <div className="stats">
        <Stat label="Events" value={formatNumber(events, 0)} />
        {!isPointEvents && <Stat label="Total time" value={formatValue(minutes.reduce<number>((a, v) => a + (v ?? 0), 0), "min")} />}
        {!isPointEvents && <Stat label={`Average per ${m.per} with data`} value={formatValue(average(minutes), "min")} />}
      </div>
      {series.length > 0 && !isPointEvents ? (
        <>
          <Legend items={series} />
          <StackedBars data={rows as never} series={series} unit="min" />
        </>
      ) : isPointEvents ? (
        <DailyBars data={m.points as never} dataKey="count" color={C.blue} unit="" label="Events" />
      ) : (
        <DailyBars
          data={m.points as never}
          dataKey="minutes"
          color={C.blue}
          unit="min"
          label="Time"
          extraRows={(p) => [{ label: "Events", value: String(p.count) }]}
        />
      )}
      <PointsTable
        rows={m.points.map((p) => [p.date, formatValue(p.minutes, "min"), String(p.count)])}
        head={[m.per === "night" ? "In bed" : "Time", "Events"]}
      />
    </>
  );
}

function PointsTable({ rows, head }: { rows: string[][]; head: string[] }) {
  return (
    <TableToggle>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            {head.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...rows]
            .reverse()
            .filter((r) => r.slice(1).some((c) => c !== "—" && c !== "0"))
            .map((r) => (
              <tr key={r[0]}>
                <td>{formatDate(r[0], true)}</td>
                {r.slice(1).map((c, i) => (
                  <td key={i}>{c}</td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>
    </TableToggle>
  );
}

export function Explore({ range, selected, onSelect }: { range: DateRange; selected: string | null; onSelect: (id: string) => void }) {
  const types = useApi<TypesData>("/api/types");
  const [query, setQuery] = useState("");
  const groups = useMemo(() => groupTypes(types.data?.types ?? [], query), [types.data, query]);

  if (types.error) return <ErrorState message={types.error} />;
  const entry = types.data?.types.find((t) => t.id === selected) ?? null;

  return (
    <div className="explore">
      <aside className="explore-list" aria-label="Health data types">
        <input
          type="search"
          placeholder="Search types…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search types"
        />
        {types.data && (
          <p className="muted small">
            {types.data.types.length} of {types.data.catalog_size} types have data
            {types.data.catalog_source === "builtin" && " (type catalog not found; using built-in list)"}
          </p>
        )}
        {!types.data && <div className="skeleton" style={{ height: 320 }} />}
        {types.data && types.data.types.length === 0 && <EmptyState compact />}
        {groups.map((g) => (
          <div key={g.group} className="explore-group">
            <h3>{g.group}</h3>
            <ul>
              {g.types.map((t) => (
                <li key={t.id}>
                  <button type="button" aria-current={t.id === selected} onClick={() => onSelect(t.id)}>
                    <span>{t.name}</span>
                    <span className="muted small">
                      {formatNumber(t.count, 0)} · {t.latest ? formatAgo(t.latest) : "—"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {types.data && types.data.types.length > 0 && groups.length === 0 && <p className="muted">No types match “{query}”.</p>}
      </aside>
      <div className="explore-main">
        {entry ? (
          <MetricView entry={entry} range={range} />
        ) : (
          <Card title="Explore everything">
            <p className="muted">
              Every Apple Health type the iPhone app has synced shows up on the left, grouped like the Health app.
              Pick one to chart it. Totals (steps, nutrition, minutes) are summed per day; measurements (heart rate,
              VO2 max) show the daily average and range; events (symptoms, mindful sessions) show time and count.
            </p>
            {types.data?.types[0] && (
              <p className="muted small">Latest sample overall: {formatDate(types.data.types.map((t) => t.latest ?? "").sort().pop()!.slice(0, 10), true)}</p>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
