/**
 * The single entry point for rendering ANY backend response.
 *
 * There is one switch on `visualization.type` and nothing else: no per-query
 * special cases, which is the test of whether the output contract is really
 * frontend-friendly.
 */

import type { Datum, Visualization } from "../types/api";
import {
  BarOrHistogram,
  GroupedBar,
  ScatterPlot,
  TimeSeries,
} from "./CartesianCharts";
import { NetworkGraph } from "./NetworkGraph";

interface Props {
  visualization: Visualization;
  onSelect: (datum: Datum) => void;
  selectedKey: string | null;
}

export function VisualizationRenderer({ visualization, onSelect, selectedKey }: Props) {
  const props = { visualization, onSelect, selectedKey };

  switch (visualization.type) {
    case "bar_chart":
    case "histogram":
      return <BarOrHistogram {...props} />;
    case "grouped_bar_chart":
      return <GroupedBar {...props} />;
    case "time_series":
      return <TimeSeries {...props} />;
    case "scatter_plot":
      return <ScatterPlot {...props} />;
    case "network_graph":
      return <NetworkGraph visualization={visualization} onSelect={onSelect} />;
    default:
      return (
        <div className="flex h-full items-center justify-center text-slate-500">
          No renderer is registered for “{visualization.type}”.
        </div>
      );
  }
}
