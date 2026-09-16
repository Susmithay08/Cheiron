/** Backend-shaped fixtures, copied from real /analyze responses. */

import type { AnalyzeResponse, Visualization } from "../types/api";

export function meta(overrides: Partial<Visualization["metadata"]> = {}) {
  return {
    source: "ClinicalTrials.gov",
    source_api: "https://clinicaltrials.gov/api/v2/studies",
    metric: "trial_count",
    unit: "trials",
    sort: { field: "trial_count", direction: "desc" as const },
    time_granularity: null,
    grouping: "phase",
    filters_applied: {},
    search_terms: ["melanoma"],
    studies_retrieved: 3,
    studies_matched: 3,
    truncated: false,
    studies_available: 3,
    assumptions: [],
    notes: [],
    ...overrides,
  };
}

const citation = (nct: string) => ({
  nct_id: nct,
  field: "protocolSection.designModule.phases",
  value: "Phase 3",
  excerpt: `A phase 3 study (${nct})`,
  url: `https://clinicaltrials.gov/study/${nct}`,
});

export const BAR_CHART: Visualization = {
  type: "bar_chart",
  title: "Melanoma Trials by Phase (Number of Trials)",
  description: "Studies grouped by phase.",
  encoding: {
    x: { field: "phase", type: "nominal", title: "Phase" },
    y: { field: "trial_count", type: "quantitative", title: "Number of Trials" },
  },
  data: [
    {
      phase: "Phase 3",
      trial_count: 2,
      citations: [citation("NCT00000001"), citation("NCT00000002")],
      supporting_trial_count: 2,
      supporting_nct_ids: ["NCT00000001", "NCT00000002"],
    },
    {
      phase: "Phase 1",
      trial_count: 1,
      citations: [citation("NCT00000003")],
      supporting_trial_count: 1,
      supporting_nct_ids: ["NCT00000003"],
    },
  ],
  metadata: meta(),
};

export const TIME_SERIES: Visualization = {
  type: "time_series",
  title: "Pembrolizumab Trials per Start Year",
  description: "Studies by start year.",
  encoding: {
    x: { field: "year", type: "temporal", title: "Start Year" },
    y: { field: "trial_count", type: "quantitative", title: "Number of Trials" },
  },
  data: [
    { year: "2020", trial_count: 2, citations: [citation("NCT00000001")], supporting_trial_count: 2, supporting_nct_ids: ["NCT00000001", "NCT00000002"] },
    { year: "2021", trial_count: 0, citations: [], supporting_trial_count: 0, supporting_nct_ids: [] },
    { year: "2022", trial_count: 1, citations: [citation("NCT00000003")], supporting_trial_count: 1, supporting_nct_ids: ["NCT00000003"] },
  ],
  metadata: meta({ grouping: "year", time_granularity: "year" }),
};

export const GROUPED_BAR: Visualization = {
  type: "grouped_bar_chart",
  title: "Ozempic vs Wegovy Trials by Phase",
  description: "Two independent searches.",
  encoding: {
    x: { field: "phase", type: "nominal", title: "Phase" },
    y: { field: "trial_count", type: "quantitative", title: "Number of Trials" },
    series: { field: "series", type: "nominal", title: "Series" },
  },
  data: [
    { phase: "Phase 3", series: "Ozempic", trial_count: 4, citations: [citation("NCT00000001")], supporting_trial_count: 4, supporting_nct_ids: ["NCT00000001"] },
    { phase: "Phase 3", series: "Wegovy", trial_count: 2, citations: [citation("NCT00000002")], supporting_trial_count: 2, supporting_nct_ids: ["NCT00000002"] },
  ],
  metadata: meta(),
};

export const HISTOGRAM: Visualization = {
  type: "histogram",
  title: "Enrollment Distribution",
  description: "Binned enrollment.",
  encoding: {
    x: { field: "bin", type: "ordinal", title: "Enrollment (binned)" },
    y: { field: "trial_count", type: "quantitative", title: "Number of Trials" },
  },
  data: [
    { bin: "0–50", trial_count: 3, citations: [citation("NCT00000001")], supporting_trial_count: 3, supporting_nct_ids: ["NCT00000001"] },
    { bin: "50–100", trial_count: 0, citations: [], supporting_trial_count: 0, supporting_nct_ids: [] },
    { bin: ">100", trial_count: 1, citations: [citation("NCT00000002")], supporting_trial_count: 1, supporting_nct_ids: ["NCT00000002"] },
  ],
  metadata: meta({ grouping: "enrollment" }),
};

export const SCATTER: Visualization = {
  type: "scatter_plot",
  title: "Enrollment vs Start Year",
  description: "One point per study.",
  encoding: {
    x: { field: "start_year", type: "quantitative", title: "Start Year" },
    y: { field: "enrollment", type: "quantitative", title: "Enrollment" },
    color: { field: "phase", type: "nominal", title: "Phase" },
  },
  data: [
    { start_year: 2020, enrollment: 120, nct_id: "NCT00000001", label: "Study one", phase: "Phase 3", citations: [citation("NCT00000001")], supporting_trial_count: 1, supporting_nct_ids: ["NCT00000001"] },
    { start_year: 2021, enrollment: 0, nct_id: "NCT00000002", label: "Study two", phase: "Phase 1", citations: [citation("NCT00000002")], supporting_trial_count: 1, supporting_nct_ids: ["NCT00000002"] },
  ],
  metadata: meta({ metric: "enrollment", unit: "participants", grouping: null, sort: null }),
};

export const NETWORK: Visualization = {
  type: "network_graph",
  title: "Sponsor ↔ Drug Network for Diabetes Trials",
  description: "Nodes are entities.",
  encoding: {
    node_id: "id",
    node_label: "label",
    node_group: "group",
    edge_source: "source",
    edge_target: "target",
    edge_weight: "weight",
  },
  data: [],
  nodes: [
    { id: "Merck", label: "Merck", group: "sponsor", degree: 1, trial_count: 2 },
    { id: "Pembrolizumab", label: "Pembrolizumab", group: "drug", degree: 1, trial_count: 2 },
  ],
  edges: [
    {
      source: "Merck",
      target: "Pembrolizumab",
      weight: 2,
      citations: [citation("NCT00000001")],
      supporting_trial_count: 2,
      supporting_nct_ids: ["NCT00000001", "NCT00000002"],
    },
  ],
  metadata: meta({ metric: "weight", unit: "co-occurring trials", grouping: "entity_pair" }),
};

export const ALL_VISUALIZATIONS: Visualization[] = [
  BAR_CHART,
  GROUPED_BAR,
  TIME_SERIES,
  SCATTER,
  HISTOGRAM,
  NETWORK,
];

export function responseFor(
  visualization: Visualization,
  planOverrides: Partial<AnalyzeResponse["meta"]["plan"]> = {},
): AnalyzeResponse {
  return {
    visualization,
    meta: {
      request_id: "abc123def456",
      query: "melanoma by phase",
      source: "clinicaltrials.gov",
      source_api: "https://clinicaltrials.gov/api/v2",
      elapsed_ms: 812,
      plan: {
        intent: "distribution",
        search_terms: ["melanoma"],
        dimension: "phase",
        metric: "trial_count",
        relationship: null,
        filters: {},
        interpretation: "Melanoma trials grouped by phase.",
        planner_mode: "llm",
        intent_hint: null,
        intent_hint_applied: null,
        ...planOverrides,
      },
    },
  };
}
