import { rangeQuery, useApi, type NightData } from "../api";
import { C, StackedBars, TableToggle } from "../components/charts";
import { Card, Legend, Load, Notice, Stat } from "../components/ui";
import { average, formatDate, formatMinutes, formatTime } from "../lib/format";
import type { DateRange } from "../lib/range";

type SleepData = { nights: NightData[] };

export const SLEEP_STAGES = [
  { key: "deep_min", label: "Deep", color: C.deep },
  { key: "core_min", label: "Core", color: C.core },
  { key: "rem_min", label: "REM", color: C.rem },
  { key: "unspecified_min", label: "Asleep (no stage)", color: C.asleep },
  { key: "awake_min", label: "Awake", color: C.awake },
];

export function Sleep({ range }: { range: DateRange }) {
  const state = useApi<SleepData>(`/api/sleep?${rangeQuery(range)}`);
  return (
    <div className="grid">
      <Card
        title="Sleep stages"
        subtitle="Per night. A night is named after the morning it ends on (noon to noon)."
        wide
      >
        <Load state={state} isEmpty={(d) => d.nights.every((n) => !n.has_data)} height={300}>
          {(d) => {
            const nights = d.nights.filter((n) => n.has_data);
            const unstaged = nights.filter((n) => !n.staged).length;
            const avg = (k: keyof NightData) => average(nights.map((n) => n[k] as number));
            return (
              <>
                <div className="stats">
                  <Stat label="Average asleep" value={formatMinutes(avg("asleep_min"))} />
                  <Stat label="Average deep" value={formatMinutes(average(nights.filter((n) => n.staged).map((n) => n.deep_min)))} />
                  <Stat label="Average REM" value={formatMinutes(average(nights.filter((n) => n.staged).map((n) => n.rem_min)))} />
                  <Stat label="Average in bed" value={formatMinutes(avg("in_bed_min"))} />
                  <Stat label="Nights recorded" value={`${nights.length} of ${d.nights.length}`} />
                </div>
                <Legend items={SLEEP_STAGES.map((s) => ({ label: s.label, color: s.color }))} />
                <StackedBars
                  data={d.nights as never}
                  xKey="night"
                  series={SLEEP_STAGES}
                  unit="h"
                  height={300}
                  title={(n) => `Night ending ${formatDate(String(n.night), true)}`}
                  footer={(n) =>
                    n.has_data
                      ? [
                          { label: "Total asleep", value: formatMinutes(n.asleep_min as number) },
                          { label: "In bed", value: formatMinutes(n.in_bed_min as number) },
                          { label: "Bed → up", value: `${formatTime(String(n.start))} → ${formatTime(String(n.end))}` },
                        ]
                      : [{ label: "No data", value: "" }]
                  }
                />
                {unstaged > 0 && (
                  <Notice>
                    {unstaged} {unstaged === 1 ? "night has" : "nights have"} no stage data (probably no Apple Watch
                    that night), so only total sleep is shown.
                  </Notice>
                )}
                <TableToggle>
                  <table>
                    <thead>
                      <tr>
                        <th>Night</th>
                        <th>Asleep</th>
                        <th>Deep</th>
                        <th>Core</th>
                        <th>REM</th>
                        <th>Awake</th>
                        <th>In bed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...nights].reverse().map((n) => (
                        <tr key={n.night}>
                          <td>{formatDate(n.night, true)}</td>
                          <td>{formatMinutes(n.asleep_min)}</td>
                          <td>{formatMinutes(n.deep_min)}</td>
                          <td>{formatMinutes(n.core_min)}</td>
                          <td>{formatMinutes(n.rem_min)}</td>
                          <td>{formatMinutes(n.awake_min)}</td>
                          <td>{formatMinutes(n.in_bed_min)}</td>
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
    </div>
  );
}
