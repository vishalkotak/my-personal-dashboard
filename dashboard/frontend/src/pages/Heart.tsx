import { rangeQuery, useApi, type HeartDay } from "../api";
import { C, TrendLines } from "../components/charts";
import { Card, Load, Stat } from "../components/ui";
import { average, formatValue } from "../lib/format";
import type { DateRange } from "../lib/range";

type HeartData = { days: HeartDay[] };

export function Heart({ range }: { range: DateRange }) {
  const state = useApi<HeartData>(`/api/heart?${rangeQuery(range)}`);
  const none = (k: keyof HeartDay) => (d: HeartData) => d.days.every((x) => x[k] == null);
  return (
    <div className="grid">
      <Card title="Heart rate" subtitle="Daily average, with the day's lowest–highest range shaded" wide>
        <Load state={state} isEmpty={none("hr_avg")}>
          {(d) => (
            <>
              <div className="stats">
                <Stat label="Average" value={formatValue(average(d.days.map((x) => x.hr_avg)), "bpm")} />
                <Stat label="Lowest" value={formatValue(Math.min(...d.days.map((x) => x.hr_min ?? Infinity)), "bpm")} />
                <Stat label="Highest" value={formatValue(Math.max(...d.days.map((x) => x.hr_max ?? -Infinity)), "bpm")} />
              </div>
              <TrendLines
                data={d.days as never}
                lines={[{ key: "hr_avg", label: "Average", color: C.red }]}
                band={{ min: "hr_min", max: "hr_max", label: "Range" }}
                unit="bpm"
              />
            </>
          )}
        </Load>
      </Card>
      <Card title="Resting heart rate" subtitle="Lower usually means better cardiovascular fitness">
        <Load state={state} isEmpty={none("resting")}>
          {(d) => (
            <>
              <div className="stats">
                <Stat label="Average" value={formatValue(average(d.days.map((x) => x.resting)), "bpm")} />
              </div>
              <TrendLines data={d.days as never} lines={[{ key: "resting", label: "Resting HR", color: C.red }]} unit="bpm" />
            </>
          )}
        </Load>
      </Card>
      <Card title="Heart rate variability" subtitle="SDNN, daily average. Higher generally means better recovered">
        <Load state={state} isEmpty={none("hrv")}>
          {(d) => (
            <>
              <div className="stats">
                <Stat label="Average" value={formatValue(average(d.days.map((x) => x.hrv)), "ms")} />
              </div>
              <TrendLines data={d.days as never} lines={[{ key: "hrv", label: "HRV", color: C.violet }]} unit="ms" />
            </>
          )}
        </Load>
      </Card>
    </div>
  );
}
