/** One palette for every chart, so the whole app reads as a single system. */
export const SERIES_COLORS = [
  "#2563eb",
  "#f97316",
  "#059669",
  "#9333ea",
  "#dc2626",
  "#0891b2",
];

export const GROUP_COLORS: Record<string, string> = {
  sponsor: "#2563eb",
  drug: "#f97316",
  condition: "#059669",
};

export const colorFor = (index: number) => SERIES_COLORS[index % SERIES_COLORS.length];

export const groupColor = (group: string, index = 0) =>
  GROUP_COLORS[group] ?? colorFor(index);

export const AXIS = {
  stroke: "#94a3b8",
  tick: { fill: "#475569", fontSize: 12 },
  grid: "#e2e8f0",
};
