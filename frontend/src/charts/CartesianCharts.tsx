/**
 * Recharts renderers for the four cartesian chart types.
 *
 * Every component reads field names from `visualization.encoding` rather than
 * hard-coding them, which is the whole point of the backend contract.
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
import { AXIS, colorFor } from "./palette";

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

function ChartTooltip({ active, payload, unit }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-sm shadow-lg">
      <p className="font-medium text-slate-900">{payload[0].payload.__label ?? payload[0].payload[Object.keys(payload[0].payload)[0]]}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: <span className="font-semibold">{entry.value?.toLocaleString()}</span> {unit}
        </p>
      ))}
      <p className="mt-1 text-xs text-slate-400">Click a point for its sources</p>
    </div>
  );
}

export function BarOrHistogram({ visualization, onSelect, selectedKey }: Props) {
  const xField = visualization.encoding.x!.field;
  const yField = visualization.encoding.y!.field;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={visualization.data} margin={{ top: 8, right: 16, bottom: 56, left: 8 }}>
        <CartesianGrid stroke={AXIS.grid} vertical={false} />
        <XAxis
          dataKey={xField}
          stroke={AXIS.stroke}
          tick={{ ...AXIS.tick }}
          angle={-35}
          textAnchor="end"
          interval={0}
          height={70}
        />
        <YAxis stroke={AXIS.stroke} tick={AXIS.tick} allowDecimals={false} />
        <Tooltip content={<ChartTooltip unit={visualization.metadata.unit} />} cursor={{ fill: "#f1f5f9" }} />
        <Bar dataKey={yField} radius={[4, 4, 0, 0]} onClick={(_, index) => onSelect(visualization.data[index])}>
          {visualization.data.map((datum, index) => (
            <Cell
              key={index}
              cursor="pointer"
              fill={keyOf(datum, visualization) === selectedKey ? "#1e293b" : colorFor(0)}
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
      <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 56, left: 8 }}>
        <CartesianGrid stroke={AXIS.grid} vertical={false} />
        <XAxis dataKey={xField} stroke={AXIS.stroke} tick={AXIS.tick} angle={-35} textAnchor="end" interval={0} height={70} />
        <YAxis stroke={AXIS.stroke} tick={AXIS.tick} allowDecimals={false} />
        <Tooltip content={<ChartTooltip unit={visualization.metadata.unit} />} cursor={{ fill: "#f1f5f9" }} />
        <Legend verticalAlign="top" height={32} />
        {seriesNames.map((name, index) => (
          <Bar
            key={name}
            dataKey={name}
            fill={colorFor(index)}
            radius={[4, 4, 0, 0]}
            cursor="pointer"
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
          margin={{ top: 8, right: 24, bottom: 24, left: 8 }}
          onClick={(state: any) => {
            const index = state?.activeTooltipIndex;
            if (typeof index === "number") onSelect(visualization.data[index]);
          }}
        >
          <CartesianGrid stroke={AXIS.grid} vertical={false} />
          <XAxis dataKey={xField} stroke={AXIS.stroke} tick={AXIS.tick} />
          <YAxis stroke={AXIS.stroke} tick={AXIS.tick} allowDecimals={false} />
          <Tooltip content={<ChartTooltip unit={visualization.metadata.unit} />} />
          <Line
            type="monotone"
            dataKey={yField}
            stroke={colorFor(0)}
            strokeWidth={2.5}
            dot={{ r: 3, cursor: "pointer" }}
            activeDot={{ r: 6, cursor: "pointer" }}
          />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  const { seriesNames, rows } = pivotBySeries(visualization);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={{ top: 8, right: 24, bottom: 24, left: 8 }}>
        <CartesianGrid stroke={AXIS.grid} vertical={false} />
        <XAxis dataKey={xField} stroke={AXIS.stroke} tick={AXIS.tick} />
        <YAxis stroke={AXIS.stroke} tick={AXIS.tick} allowDecimals={false} />
        <Tooltip content={<ChartTooltip unit={visualization.metadata.unit} />} />
        <Legend verticalAlign="top" height={32} />
        {seriesNames.map((name, index) => (
          <Line key={name} type="monotone" dataKey={name} stroke={colorFor(index)} strokeWidth={2.5} dot={false} />
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

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 8, right: 24, bottom: 32, left: 8 }}>
        <CartesianGrid stroke={AXIS.grid} />
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
          scale="log"
          domain={[1, "dataMax"]}
          allowDataOverflow
        />
        <Tooltip
          cursor={{ strokeDasharray: "3 3" }}
          content={({ active, payload }: any) => {
            if (!active || !payload?.length) return null;
            const point = payload[0].payload;
            return (
              <div className="max-w-xs rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-sm shadow-lg">
                <p className="font-medium text-slate-900">{point.nct_id}</p>
                <p className="text-slate-600">{String(point.label).slice(0, 110)}</p>
                <p className="mt-1 text-slate-500">
                  {xField}: {point[xField]} · {yField}: {Number(point[yField]).toLocaleString()}
                </p>
              </div>
            );
          }}
        />
        {groups.length > 1 && <Legend verticalAlign="top" height={32} />}
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
            fillOpacity={0.65}
            cursor="pointer"
            onClick={(point: any) => onSelect(point.payload ?? point)}
          />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}
