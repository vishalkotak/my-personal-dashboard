import { rangeQuery, useApi, type CumulativePoint, type Daily } from "../api";
import { C, DailyBars, TableToggle } from "../components/charts";
import { Card, Load, Stat } from "../components/ui";
import { average, formatDate, formatValue } from "../lib/format";
import type { DateRange } from "../lib/range";

const empty = (d: Daily<CumulativePoint>) => d.points.every((p) => p.value == null);

function ActivityChart({
  range,
  type,
  title,
  color,
  unit,
  scale = 1,
  label,
}: {
  range: DateRange;
  type: string;
  title: string;
  color: string;
  unit: string;
  scale?: number;
  label: string;
}) {
  const state = useApi<Daily<CumulativePoint>>(`/api/daily?${rangeQuery(range, { type })}`);
  return (
    <Card title={title} subtitle="Per day · dashed line is the daily average" wide>
      <Load state={state} isEmpty={empty}>
        {(d) => {
          const pts = d.points.map((p) => ({
            ...p,
            value: p.value == null ? null : p.value * scale,
          }));
          const vals = pts.map((p) => p.value);
          const avg = average(vals);
          const best = pts.reduce<(typeof pts)[number] | null>((b, p) => (p.value != null && (!b || p.value > (b.value ?? 0)) ? p : b), null);
          const total = vals.reduce<number>((a, v) => a + (v ?? 0), 0);
          return (
            <>
              <div className="stats">
                <Stat label="Daily average" value={formatValue(avg, unit)} />
                <Stat label="Total" value={formatValue(total, unit)} />
                <Stat label="Best day" value={formatValue(best?.value, unit)} hint={best ? formatDate(best.date, true) : undefined} />
              </div>
              <DailyBars
                data={pts}
                dataKey="value"
                color={color}
                unit={unit}
                label={label}
                average={avg}
              />
              <TableToggle>
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>{label}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...pts].reverse().map((p) => (
                      <tr key={p.date}>
                        <td>{formatDate(p.date, true)}</td>
                        <td>{formatValue(p.value, unit)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableToggle>
            </>
          );
        }}
      </Load>
    </Card>
  );
}

export function Activity({ range }: { range: DateRange }) {
  return (
    <>
      <div className="grid">
        <ActivityChart range={range} type="steps" title="Steps" color={C.blue} unit="steps" label="Steps" />
        <ActivityChart range={range} type="distance" title="Walking + running distance" color={C.aqua} unit="km" scale={0.001} label="Distance" />
        <ActivityChart range={range} type="active_energy" title="Active energy" color={C.orange} unit="kcal" label="Active energy" />
      </div>
    </>
  );
}
