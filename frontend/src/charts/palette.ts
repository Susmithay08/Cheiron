/**
 * Chart colours, mirrored from the CSS design tokens in `index.css`.
 *
 * Recharts and the SVG network graph need real values rather than Tailwind
 * classes, so the tokens are duplicated here — and nowhere else — to keep every
 * chart inside the same purple system as the rest of the UI.
 */

export const TOKENS = {
  canvas: "#0D0D14",
  card: "#16161F",
  brand: "#7C3AED",
  brandBright: "#9F67FF",
  brandSoft: "#C084FC",
  brandDeep: "#4F1D96",
  ink: "#F0F0FF",
  muted: "#8888AA",
  edge: "#2A2A3D",
  danger: "#FF4444",
} as const;

/** Multi-series ramp: distinguishable in sequence, still one family. */
export const SERIES_COLORS = [
  TOKENS.brand,
  TOKENS.brandBright,
  TOKENS.brandSoft,
  TOKENS.brandDeep,
  "#E9D5FF",
  "#6D28D9",
];

/** Node colours by entity kind in the network graph. */
export const GROUP_COLORS: Record<string, string> = {
  sponsor: TOKENS.brand,
  drug: TOKENS.brandSoft,
  condition: TOKENS.brandBright,
};

export const colorFor = (index: number) => SERIES_COLORS[index % SERIES_COLORS.length];

export const groupColor = (group: string, index = 0) => GROUP_COLORS[group] ?? colorFor(index);

/** Axis styling shared by every cartesian chart. */
export const AXIS = {
  stroke: TOKENS.edge,
  tick: { fill: TOKENS.muted, fontSize: 12 },
  grid: TOKENS.edge,
  selected: TOKENS.brandSoft,
  cursor: "rgba(124, 58, 237, 0.12)",
};
