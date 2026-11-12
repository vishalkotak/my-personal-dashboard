import { rangeQuery, useApi, type WorkoutsData } from "../api";
import { C, DailyBars } from "../components/charts";
import { Card, Load, Stat } from "../components/ui";
import { formatDate, formatMinutes, formatTime } from "../lib/format";
import type { DateRange } from "../lib/range";

export function Workouts({ range }: { range: DateRange }) {
  const state = useApi<WorkoutsData>(`/api/workouts?${rangeQuery(range)}`);
  const empty = (d: WorkoutsData) => d.workouts.length === 0;
  return (
    <div className="grid">
      <Card title="Weekly workout minutes" subtitle="Weeks start on Monday" wide>
        <Load state={state} isEmpty={empty}>
          {(d) => {
            const total = d.workouts.reduce((a, w) => a + w.duration_min, 0);
            const weeks = d.weekly.length || 1;
            return (
              <>
                <div className="stats">
                  <Stat label="Workouts" value={String(d.workouts.length)} />
                  <Stat label="Total time" value={formatMinutes(total)} />
                  <Stat label="Per week" value={formatMinutes(total / weeks)} />
                </div>
                <DailyBars
                  data={d.weekly as never}
                  xKey="week_start"
                  dataKey="minutes"
                  color={C.blue}
                  unit="min"
                  label="Minutes"
                  extraRows={(w) => [{ label: "Workouts", value: String(w.count) }]}
                />
              </>
            );
          }}
        </Load>
      </Card>
      <Card title="By type">
        <Load state={state} isEmpty={empty}>
          {(d) => {
            const max = Math.max(...d.by_type.map((t) => t.minutes), 1);
            return (
              <ul className="hbars">
                {d.by_type.map((t) => (
                  <li key={t.name}>
                    <div className="hbar-label">
                      <span>{t.name}</span>
                      <span className="muted">
                        {t.count}× · {formatMinutes(t.minutes)}
                      </span>
                    </div>
                    <div className="hbar-track">
                      <div className="hbar" style={{ width: `${(t.minutes / max) * 100}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            );
          }}
        </Load>
      </Card>
      <Card title="Recent workouts">
        <Load state={state} isEmpty={empty}>
          {(d) => (
            <div className="table-wrap scroll">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Start</th>
                    <th>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {d.workouts.map((w) => (
                    <tr key={w.start}>
                      <td>{formatDate(w.date, true)}</td>
                      <td>{w.name}</td>
                      <td>{formatTime(w.start)}</td>
                      <td>{formatMinutes(w.duration_min)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Load>
      </Card>
    </div>
  );
}
