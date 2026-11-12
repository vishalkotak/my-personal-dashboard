import type { ReactNode } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDate, formatNumber, formatValue, tickInterval } from "../lib/format";

// Colors are CSS variables so light/dark mode swap in one place (styles.css).
export const C = {
  blue: "var(--series-1)",
  orange: "var(--series-2)",
  aqua: "var(--series-3)",
  yellow: "var(--series-4)",
  magenta: "var(--series-5)",
  violet: "var(--series-7)",
  red: "var(--series-8)",
  band: "var(--band)",
  deep: "var(--sleep-deep)",
  core: "var(--sleep-core)",
  rem: "var(--sleep-rem)",
  asleep: "var(--sleep-asleep)",
  awake: "var(--sleep-awake)",
  inbed: "var(--sleep-inbed)",
};

const AXIS = { stroke: "var(--axis)", fontSize: 12, tickLine: false, axisLine: false } as const;
const GRID = <CartesianGrid vertical={false} stroke="var(--grid)" />;

type Row = Record<string, unknown>;

export interface TooltipRow {
  label: string;
  value: string;
  color?: string;
}

/** Shared tooltip shell. `rows(datum)` decides what to show for the hovered point. */
function makeTooltip(rows: (d: Row) => TooltipRow[], titleFor: (d: Row) => string) {
  return function ChartTooltip({ active, payload }: { active?: boolean; payload?: readonly { payload?: Row }[] }) {
    const d = payload?.[0]?.payload;
    if (!active || !d) return null;
    const list = rows(d);
    return (
      <div className="tooltip">
        <div className="tooltip-title">{titleFor(d)}</div>
        {list.map((r) => (
          <div className="tooltip-row" key={r.label}>
            {r.color && <span className="swatch" style={{ background: r.color }} />}
            <span className="tooltip-label">{r.label}</span>
            <span className="tooltip-value">{r.value}</span>
          </div>
        ))}
      </div>
    );
  };
}

const dateTitle = (key: string) => (d: Row) => formatDate(String(d[key]), true);

function xAxis(xKey: string, n: number, fmt: (s: string) => string = (s) => formatDate(s)) {
  return <XAxis dataKey={xKey} {...AXIS} interval={tickInterval(n)} tickFormatter={fmt} minTickGap={8} />;
}

function yAxis(unit: string, width = 48, domain?: [number | string, number | string]) {
  return (
    <YAxis
      {...AXIS}
      width={width}
      domain={domain}
      tickFormatter={(v: number) => (unit === "h" ? `${v}h` : formatNumber(v))}
      allowDecimals={unit !== ""}
    />
  );
}

export function DailyBars({
  data,
  dataKey,
  color,
  unit,
  label,
  average,
  height = 240,
  xKey = "date",
  extraRows,
}: {
  data: Row[];
  dataKey: string;
  color: string;
  unit: string;
  label: string;
  average?: number | null;
  height?: number;
  xKey?: string;
  extraRows?: (d: Row) => TooltipRow[];
}) {
  const Tip = makeTooltip(
    (d) => [
      { label, value: formatValue(d[dataKey] as number | null, unit), color },
      ...(extraRows ? extraRows(d) : []),
    ],
    xKey === "week_start" ? (d) => `Week of ${formatDate(String(d[xKey]), true)}` : dateTitle(xKey),
  );
  const many = data.length > 120;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={many ? 0 : "18%"}>
        {GRID}
        {xAxis(xKey, data.length)}
        {yAxis(unit)}
        <Tooltip content={Tip} cursor={{ fill: "var(--hover)" }} isAnimationActive={false} />
        <Bar dataKey={dataKey} fill={color} radius={many ? 0 : [4, 4, 0, 0]} isAnimationActive={false} />
        {average != null && (
          <ReferenceLine y={average} stroke="var(--text-2)" strokeDasharray="4 4" ifOverflow="extendDomain" />
        )}
      </BarChart>
    </ResponsiveContainer>
  );
}

export interface LineSpec {
  key: string;
  label: string;
  color: string;
  dashed?: boolean;
}

export function TrendLines({
  data,
  lines,
  unit,
  band,
  height = 240,
  domain = ["auto", "auto"],
  xKey = "date",
  dots,
}: {
  data: Row[];
  lines: LineSpec[];
  unit: string;
  band?: { min: string; max: string; label: string };
  height?: number;
  domain?: [number | string, number | string];
  xKey?: string;
  dots?: boolean;
}) {
  const rows = (d: Row): TooltipRow[] => [
    ...lines.map((l) => ({ label: l.label, value: formatValue(d[l.key] as number | null, unit), color: l.color })),
    ...(band && d[band.min] != null
      ? [{ label: band.label, value: `${formatValue(d[band.min] as number, unit)} – ${formatValue(d[band.max] as number, unit)}` }]
      : []),
  ];
  const Tip = makeTooltip(rows, dateTitle(xKey));
  const sparse = data.filter((d) => lines.some((l) => d[l.key] != null)).length < data.length * 0.6;
  const showDots = dots ?? (sparse || data.length <= 31);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        {GRID}
        {xAxis(xKey, data.length)}
        {yAxis(unit, 48, domain)}
        <Tooltip content={Tip} cursor={{ stroke: "var(--axis)", strokeWidth: 1 }} isAnimationActive={false} />
        {band && (
          <Area
            dataKey={(d: Row) => (d[band.min] == null ? null : [d[band.min], d[band.max]])}
            stroke="none"
            fill={C.band}
            isAnimationActive={false}
            connectNulls={false}
            activeDot={false}
          />
        )}
        {lines.map((l) => (
          <Line
            key={l.key}
            dataKey={l.key}
            stroke={l.color}
            strokeWidth={2}
            strokeDasharray={l.dashed ? "5 4" : undefined}
            dot={showDots ? { r: 2.5, strokeWidth: 0, fill: l.color } : false}
            activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--surface)" }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export interface StackSpec {
  key: string;
  label: string;
  color: string;
}

export function StackedBars({
  data,
  series,
  unit,
  height = 260,
  xKey = "date",
  title,
  footer,
}: {
  data: Row[];
  series: StackSpec[];
  unit: string;
  height?: number;
  xKey?: string;
  title?: (d: Row) => string;
  footer?: (d: Row) => TooltipRow[];
}) {
  const Tip = makeTooltip(
    (d) => [
      ...series
        .filter((s) => d[s.key] != null && (d[s.key] as number) > 0)
        .map((s) => ({ label: s.label, value: formatValue(d[s.key] as number, unit === "h" ? "min" : unit), color: s.color }))
        .reverse(),
      ...(footer ? footer(d) : []),
    ],
    title ?? dateTitle(xKey),
  );
  const many = data.length > 120;
  // Values arrive in minutes; plot hours when unit is "h".
  const plotted =
    unit === "h"
      ? data.map((d) => {
          const o: Row = { ...d };
          for (const s of series) o[`${s.key}__h`] = d[s.key] == null ? null : (d[s.key] as number) / 60;
          return o;
        })
      : data;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={plotted} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={many ? 0 : "18%"}>
        {GRID}
        {xAxis(xKey, data.length)}
        {yAxis(unit, 40)}
        <Tooltip content={Tip} cursor={{ fill: "var(--hover)" }} isAnimationActive={false} />
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={unit === "h" ? `${s.key}__h` : s.key}
            stackId="a"
            fill={s.color}
            stroke={many ? "none" : "var(--surface)"}
            strokeWidth={many ? 0 : 1}
            radius={!many && i === series.length - 1 ? [4, 4, 0, 0] : 0}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Sparkline({ points, color, kind = "line" }: { points: { date: string; value: number | null }[]; color: string; kind?: "line" | "bar" }) {
  const has = points.some((p) => p.value != null);
  if (!has) return <div className="spark spark-empty" aria-hidden="true" />;
  return (
    <div className="spark" aria-hidden="true">
      <ResponsiveContainer width="100%" height={44}>
        {kind === "bar" ? (
          <BarChart data={points} margin={{ top: 2, right: 0, bottom: 0, left: 0 }} barCategoryGap="20%">
            <YAxis hide domain={[0, "dataMax"]} />
            <Bar dataKey="value" fill={color} radius={[2, 2, 0, 0]} isAnimationActive={false} />
          </BarChart>
        ) : (
          <LineChart data={points} margin={{ top: 4, right: 3, bottom: 4, left: 3 }}>
            <YAxis hide domain={["dataMin", "dataMax"]} />
            <Line dataKey="value" stroke={color} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

export function TableToggle({ children, label = "Show table" }: { children: ReactNode; label?: string }) {
  return (
    <details className="table-toggle">
      <summary>{label}</summary>
      <div className="table-wrap">{children}</div>
    </details>
  );
}
