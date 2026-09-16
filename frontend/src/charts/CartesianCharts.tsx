/**
 * Recharts renderers for the four cartesian chart types.
 *
 * Every component reads field names from `visualization.encoding` rather than
 * hard-coding them, which is the whole point of the backend contract: there is
 * no branch anywhere below that depends on what was asked.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Datum, Visualization } from "../types/api";
import { AXIS, colorFor, TOKENS } from "./palette";

interface Props {
  visualization: Visualization;
  onSelect: (datum: Datum) => void;
  selectedKey: string | null;
}

const keyOf = (datum: Datum, viz: Visualization) => {
  const x = String(datum[viz.encoding.x?.field ?? ""] ?? "");
  const series = viz.encoding.series ? String(datum.series ?? "") : "";
  return `${x}::${series}`;
};

/** Long category labels (sponsors, conditions) need truncating on the axis. */
const truncate = (value: unknown, max = 22) => {
  const text = String(value ?? "");
  return text.length > max ? `${text.slice(0, max)}…` : text;
};

/** Splits flat rows into one array per series, aligned on the x value. */
function pivotBySeries(viz: Visualization) {
  const xField = viz.encoding.x!.field;
  const yField = viz.encoding.y!.field;
  const seriesNames = [...new Set(viz.data.map((d) => String(d.series ?? "")))];
  const byX = new Map<string, Record<string, unknown>>();

  for (const row of viz.data) {
    const x = String(row[xField]);
    if (!byX.has(x)) byX.set(x, { [xField]: x });
    byX.get(x)![String(row.series ?? "")] = row[yField];
  }
  return { seriesNames, rows: [...byX.values()] };
}

function ChartTooltip({ active, payload, label, unit }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="max-w-xs rounded-control border border-edge bg-elevated px-3 py-2 text-sm shadow-card">
      <p className="font-medium text-ink">{String(label ?? "")}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}:{" "}
          <span className="font-semibold">{Number(entry.value).toLocaleString()}</span>{" "}
          <span className="text-muted">{unit}</span>
        </p>
      ))}
      <p className="mt-1 text-xs text-muted">Click for sources</p>
    </div>
  );
}

const gridProps = { stroke: AXIS.grid, strokeOpacity: 0.55, vertical: false } as const;

export function BarOrHistogram({ visualization, onSelect, selectedKey }: Props) {
  const xField = visualization.encoding.x!.field;
  const yField = visualization.encoding.y!.field;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={visualization.data} margin={{ top: 8, right: 16, bottom: 56, left: 0 }}>
        <CartesianGrid {...gridProps} />
        <XAxis
          dataKey={xField}
          stroke={AXIS.stroke}
          tick={AXIS.tick}
          tickFormatter={truncate}
          angle={-35}
          textAnchor="end"
          interval={0}
          height={70}
        />
        <YAxis stroke={AXIS.stroke} tick={AXIS.tick} allowDecimals={false} width={56} />
        <Tooltip
          content={<ChartTooltip unit={visualization.metadata.unit} />}
          cursor={{ fill: AXIS.cursor }}
        />
        <Bar
          dataKey={yField}
          radius={[4, 4, 0, 0]}
          isAnimationActive={false}
          onClick={(_, index) => onSelect(visualization.data[index])}
        >
          {visualization.data.map((datum, index) => (
            <Cell
              key={index}
              cursor="pointer"
              fill={keyOf(datum, visualization) === selectedKey ? AXIS.selected : colorFor(0)}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function GroupedBar({ visualization, onSelect }: Props) {
  const xField = visualization.encoding.x!.field;
  const { seriesNames, rows } = pivotBySeries(visualization);

  const selectRow = (xValue: string, series: string) => {
    const match = visualization.data.find(
      (d) => String(d[xField]) === xValue && String(d.series ?? "") === series,
    );
    if (match) onSelect(match);
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 56, left: 0 }}>
        <CartesianGrid {...gridProps} />
        <XAxis
          dataKey={xField}
          stroke={AXIS.stroke}
          tick={AXIS.tick}
          tickFormatter={truncate}
          angle={-35}
          textAnchor="end"
          interval={0}
          height={70}
        />
        <YAxis stroke={AXIS.stroke} tick={AXIS.tick} allowDecimals={false} width={56} />
        <Tooltip
          content={<ChartTooltip unit={visualization.metadata.unit} />}
          cursor={{ fill: AXIS.cursor }}
        />
        <Legend verticalAlign="top" height={32} wrapperStyle={{ color: TOKENS.muted }} />
        {seriesNames.map((name, index) => (
          <Bar
            key={name}
            dataKey={name}
            fill={colorFor(index)}
            radius={[4, 4, 0, 0]}
            cursor="pointer"
            isAnimationActive={false}
            onClick={(payload) => selectRow(String(payload[xField]), name)}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TimeSeries({ visualization, onSelect }: Props) {
  const xField = visualization.encoding.x!.field;
  const yField = visualization.encoding.y!.field;
  const grouped = Boolean(visualization.encoding.series);

  if (!grouped) {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={visualization.data}
          margin={{ top: 8, right: 24, bottom: 24, left: 0 }}
          onClick={(state: any) => {
            const index = state?.activeTooltipIndex;
            if (typeof index === "number" && visualization.data[index]) {
              onSelect(visualization.data[index]);
            }
          }}
        >
          <CartesianGrid {...gridProps} />
          <XAxis dataKey={xField} stroke={AXIS.stroke} tick={AXIS.tick} />
          <YAxis stroke={AXIS.stroke} tick={AXIS.tick} allowDecimals={false} width={56} />
          <Tooltip
            content={<ChartTooltip unit={visualization.metadata.unit} />}
            cursor={{ stroke: TOKENS.brandBright, strokeOpacity: 0.4 }}
          />
          <Line
            type="monotone"
            dataKey={yField}
            stroke={TOKENS.brandBright}
            strokeWidth={2.5}
            isAnimationActive={false}
            dot={{ r: 3, cursor: "pointer", fill: TOKENS.brand, stroke: TOKENS.brandBright }}
            activeDot={{ r: 6, cursor: "pointer", fill: TOKENS.brandSoft }}
          />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  const { seriesNames, rows } = pivotBySeries(visualization);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={{ top: 8, right: 24, bottom: 24, left: 0 }}>
        <CartesianGrid {...gridProps} />
        <XAxis dataKey={xField} stroke={AXIS.stroke} tick={AXIS.tick} />
        <YAxis stroke={AXIS.stroke} tick={AXIS.tick} allowDecimals={false} width={56} />
        <Tooltip
          content={<ChartTooltip unit={visualization.metadata.unit} />}
          cursor={{ stroke: TOKENS.brandBright, strokeOpacity: 0.4 }}
        />
        <Legend verticalAlign="top" height={32} wrapperStyle={{ color: TOKENS.muted }} />
        {seriesNames.map((name, index) => (
          <Line
            key={name}
            type="monotone"
            dataKey={name}
            stroke={colorFor(index)}
            strokeWidth={2.5}
            isAnimationActive={false}
            dot={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ScatterPlot({ visualization, onSelect }: Props) {
  const xField = visualization.encoding.x!.field;
  const yField = visualization.encoding.y!.field;
  const colorField = visualization.encoding.color?.field;
  const groups = colorField
    ? [...new Set(visualization.data.map((d) => String(d[colorField])))]
    : ["all"];

  // Enrollment spans several orders of magnitude, so a log scale is usually the
  // readable choice — but a log axis silently *drops* zero, and "0 enrolled" is
  // a real, reportable value. Only use it when every point is strictly positive.
  const yValues = visualization.data.map((d) => Number(d[yField]));
  const useLog = yValues.length > 0 && yValues.every((v) => Number.isFinite(v) && v > 0);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 8, right: 24, bottom: 32, left: 0 }}>
        <CartesianGrid stroke={AXIS.grid} strokeOpacity={0.55} />
        <XAxis
          type="number"
          dataKey={xField}
          name={visualization.encoding.x!.title ?? xField}
          stroke={AXIS.stroke}
          tick={AXIS.tick}
          domain={["dataMin", "dataMax"]}
        />
        <YAxis
          type="number"
          dataKey={yField}
          name={visualization.encoding.y!.title ?? yField}
          stroke={AXIS.stroke}
          tick={AXIS.tick}
          width={64}
          {...(useLog
            ? { scale: "log" as const, domain: ["auto", "auto"] as [string, string] }
            : { domain: [0, "dataMax"] as [number, string] })}
        />
        <Tooltip
          cursor={{ strokeDasharray: "3 3", stroke: TOKENS.brandBright }}
          content={({ active, payload }: any) => {
            if (!active || !payload?.length) return null;
            const point = payload[0].payload;
            return (
              <div className="max-w-xs rounded-control border border-edge bg-elevated px-3 py-2 text-sm shadow-card">
                <p className="font-mono font-medium text-brand-soft">{String(point.nct_id)}</p>
                <p className="text-muted">{String(point.label ?? "").slice(0, 110)}</p>
                <p className="mt-1 text-ink">
                  {xField}: {String(point[xField])} · {yField}:{" "}
                  {Number(point[yField]).toLocaleString()}
                </p>
              </div>
            );
          }}
        />
        {groups.length > 1 && (
          <Legend verticalAlign="top" height={32} wrapperStyle={{ color: TOKENS.muted }} />
        )}
        {groups.map((group, index) => (
          <Scatter
            key={group}
            name={group}
            data={
              colorField
                ? visualization.data.filter((d) => String(d[colorField]) === group)
                : visualization.data
            }
            fill={colorFor(index)}
            fillOpacity={0.7}
            cursor="pointer"
            isAnimationActive={false}
            onClick={(point: any) => onSelect(point.payload ?? point)}
          />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}
