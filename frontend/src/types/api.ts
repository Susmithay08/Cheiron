/**
 * Mirrors the backend visualization contract exactly.
 *
 * Note how little the renderer needs to know: a `type`, an `encoding` that
 * names the keys of each `data` row, and the rows themselves.
 */

export type ChannelType = "nominal" | "ordinal" | "quantitative" | "temporal";

export interface EncodingChannel {
  field: string;
  type: ChannelType;
  title?: string | null;
}

export interface Encoding {
  x?: EncodingChannel | null;
  y?: EncodingChannel | null;
  series?: EncodingChannel | null;
  color?: EncodingChannel | null;
  node_id?: string | null;
  node_label?: string | null;
  node_group?: string | null;
  edge_source?: string | null;
  edge_target?: string | null;
  edge_weight?: string | null;
}

export interface Citation {
  nct_id: string;
  field: string;
  value: string;
  excerpt: string;
  url: string;
}

export interface Datum {
  [key: string]: unknown;
  citations?: Citation[];
  supporting_trial_count?: number;
  supporting_nct_ids?: string[];
}

export interface GraphNode {
  id: string;
  label: string;
  group: string;
  degree: number;
  trial_count: number;
}

export interface GraphEdge extends Datum {
  source: string;
  target: string;
  weight: number;
}

export type VisualizationType =
  | "bar_chart"
  | "grouped_bar_chart"
  | "time_series"
  | "scatter_plot"
  | "histogram"
  | "network_graph";

export interface VisualizationMetadata {
  source: string;
  source_api: string;
  metric: string;
  unit: string;
  sort?: { field: string; direction: "asc" | "desc" } | null;
  time_granularity?: string | null;
  grouping?: string | null;
  filters_applied: Record<string, unknown>;
  search_terms: string[];
  studies_retrieved: number;
  studies_matched: number;
  truncated: boolean;
  assumptions: string[];
  notes: string[];
}

export interface Visualization {
  type: VisualizationType;
  title: string;
  description: string;
  encoding: Encoding;
  data: Datum[];
  nodes?: GraphNode[] | null;
  edges?: GraphEdge[] | null;
  metadata: VisualizationMetadata;
}

export interface PlanSummary {
  intent: string;
  search_terms: string[];
  dimension?: string | null;
  metric: string;
  relationship?: string | null;
  filters: Record<string, unknown>;
  interpretation: string;
  planner_mode: string;
}

export interface AnalyzeResponse {
  visualization: Visualization;
  meta: {
    request_id: string;
    query: string;
    source: string;
    source_api: string;
    elapsed_ms: number;
    plan: PlanSummary;
  };
}

export interface ApiError {
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id?: string | null;
}

export interface ExampleQuery {
  label: string;
  query: string;
  intent: string;
}
