import { rangeQuery, useApi, type BodyData } from "../api";
import { C, TrendLines } from "../components/charts";
import { Card, EmptyState, Legend, Load, Notice, Stat } from "../components/ui";
import { average, formatValue } from "../lib/format";
import type { DateRange } from "../lib/range";

export function Body({ range }: { range: DateRange }) {
  const state = useApi<BodyData>(`/api/body?${rangeQuery(range)}`);
  const none = (k: "weight" | "spo2_avg" | "temp") => (d: BodyData) => d.days.every((x) => x[k] == null);
  return (
    <div className="grid">
      <Card title="Weight" subtitle="Last weigh-in of each day" wide>
        <Load state={state} isEmpty={none("weight")}>
          {(d) => {
            const w = d.days.filter((x) => x.weight != null);
            const change = w.length > 1 ? w[w.length - 1].weight! - w[0].weight! : null;
            return (
              <>
                <div className="stats">
                  <Stat label="Latest" value={formatValue(w[w.length - 1]?.weight, "kg")} />
                  <Stat label="Average" value={formatValue(average(w.map((x) => x.weight)), "kg")} />
                  <Stat
                    label="Change over range"
                    value={change == null ? "—" : `${change > 0 ? "+" : ""}${formatValue(change, "kg", 1)}`}
                  />
                </div>
                <TrendLines data={d.days as never} lines={[{ key: "weight", label: "Weight", color: C.aqua }]} unit="kg" />
              </>
            );
          }}
        </Load>
      </Card>
      <Card title="Blood pressure" subtitle="Each paired reading (systolic and diastolic taken together)" wide>
        <Load state={state}>
          {(d) =>
            d.blood_pressure.length === 0 ? (
              <EmptyState compact />
            ) : (
              <>
                <div className="stats">
                  <Stat
                    label="Average"
                    value={`${formatValue(average(d.blood_pressure.map((b) => b.systolic)), "", 0)}/${formatValue(average(d.blood_pressure.map((b) => b.diastolic)), "", 0)} mmHg`}
                  />
                  <Stat label="Readings" value={String(d.blood_pressure.length)} />
                </div>
                <Legend
                  items={[
                    { label: "Systolic", color: C.blue },
                    { label: "Diastolic", color: C.orange },
                  ]}
                />
                <TrendLines
                  data={d.blood_pressure as never}
                  xKey="date"
                  lines={[
                    { key: "systolic", label: "Systolic", color: C.blue },
                    { key: "diastolic", label: "Diastolic", color: C.orange },
                  ]}
                  unit="mmHg"
                  dots
                />
                {d.unpaired_bp_readings > 0 && (
                  <Notice>
                    {d.unpaired_bp_readings} reading{d.unpaired_bp_readings === 1 ? "" : "s"} had no matching
                    systolic/diastolic partner and {d.unpaired_bp_readings === 1 ? "is" : "are"} not shown.
                  </Notice>
                )}
              </>
            )
          }
        </Load>
      </Card>
      <Card title="Blood oxygen" subtitle="Daily average, and the day's lowest reading">
        <Load state={state} isEmpty={none("spo2_avg")}>
          {(d) => (
            <>
              <div className="stats">
                <Stat label="Average" value={formatValue(average(d.days.map((x) => x.spo2_avg)), "%")} />
              </div>
              <Legend
                items={[
                  { label: "Average", color: C.blue },
                  { label: "Lowest", color: C.magenta, dashed: true },
                ]}
              />
              <TrendLines
                data={d.days as never}
                lines={[
                  { key: "spo2_avg", label: "Average", color: C.blue },
                  { key: "spo2_min", label: "Lowest", color: C.magenta, dashed: true },
                ]}
                unit="%"
                domain={[(min: number) => Math.max(80, Math.floor(min - 1)), 100] as never}
              />
            </>
          )}
        </Load>
      </Card>
      <Card title="Body temperature" subtitle="Daily average of manual readings">
        <Load state={state} isEmpty={none("temp")}>
          {(d) => (
            <>
              <div className="stats">
                <Stat label="Average" value={formatValue(average(d.days.map((x) => x.temp)), "°C", 2)} />
              </div>
              <TrendLines data={d.days as never} lines={[{ key: "temp", label: "Temperature", color: C.orange }]} unit="°C" dots />
            </>
          )}
        </Load>
      </Card>
    </div>
  );
}
