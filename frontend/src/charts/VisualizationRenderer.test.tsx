/**
 * Frontend contract tests: every backend visualization type must render from
 * the spec alone.
 *
 * `ResponsiveContainer` measures its parent, which jsdom cannot do, so it is
 * replaced with a fixed-size passthrough. Everything else is the real chart
 * code, driven only by `encoding` — if a renderer needed knowledge the contract
 * does not carry, these tests would be where it showed up.
 */

import { cloneElement, isValidElement } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { VisualizationRenderer } from "./VisualizationRenderer";
import type { Datum, Visualization } from "../types/api";
import {
  ALL_VISUALIZATIONS,
  BAR_CHART,
  GROUPED_BAR,
  NETWORK,
  SCATTER,
  TIME_SERIES,
  meta,
} from "../test/fixtures";

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) =>
      isValidElement(children)
        ? cloneElement(children as React.ReactElement<any>, { width: 800, height: 500 })
        : children,
  };
});

function draw(visualization: Visualization, onSelect: (d: Datum) => void = () => {}) {
  return render(
    <div style={{ width: 800, height: 500 }}>
      <VisualizationRenderer
        visualization={visualization}
        onSelect={onSelect}
        selectedKey={null}
      />
    </div>,
  );
}

describe("every visualization type", () => {
  it.each(ALL_VISUALIZATIONS.map((v) => [v.type, v] as const))(
    "renders %s from the spec alone",
    (_type, visualization) => {
      const { container } = draw(visualization);
      expect(container.querySelector("svg")).toBeTruthy();
    },
  );

  it.each(ALL_VISUALIZATIONS.map((v) => [v.type, v] as const))(
    "renders %s with an empty data set without crashing",
    (_type, visualization) => {
      const { container } = draw({ ...visualization, data: [], nodes: [], edges: [] });
      expect(container).toBeTruthy();
    },
  );
});

/**
 * Note: jsdom reports zero width for SVG text, so Recharts truncates every tick
 * label to an ellipsis. These tests therefore assert on chart *structure* — one
 * mark and one tick per datum — which is what actually proves the renderer read
 * the encoding rather than guessing.
 */
describe("encoding is honoured rather than assumed", () => {
  const marks = (container: HTMLElement, selector: string) =>
    container.querySelectorAll(selector).length;

  it("draws one bar per datum, bound to the encoded fields", () => {
    const { container } = draw(BAR_CHART);
    expect(marks(container, ".recharts-bar-rectangle")).toBe(BAR_CHART.data.length);
    expect(
      container.querySelectorAll(".recharts-xAxis .recharts-cartesian-axis-tick").length,
    ).toBe(BAR_CHART.data.length);
  });

  it("renders an arbitrary renamed field with no code change", () => {
    const renamed: Visualization = {
      ...BAR_CHART,
      encoding: {
        x: { field: "sponsor_category", type: "nominal", title: "Sponsor Category" },
        y: { field: "enrollment_sum", type: "quantitative", title: "Total Enrollment" },
      },
      data: [
        { sponsor_category: "Industry", enrollment_sum: 4200, citations: [] },
        { sponsor_category: "NIH", enrollment_sum: 900, citations: [] },
      ],
      metadata: meta({ metric: "enrollment_sum", unit: "participants" }),
    };
    const { container } = draw(renamed);
    // Nothing in the renderer knows the field names "sponsor_category" or
    // "enrollment_sum"; the marks appear purely because the encoding named them.
    expect(marks(container, ".recharts-bar-rectangle")).toBe(2);
    expect(marks(container, ".recharts-yAxis .recharts-cartesian-axis-tick")).toBeGreaterThan(0);
  });

  it("survives a datum whose encoded value is missing", () => {
    // The backend validator rejects this shape, so it should never arrive — but
    // a renderer that throws on one bad row would take the whole page with it.
    const { container } = draw({
      ...BAR_CHART,
      data: [
        { phase: "Phase 3", trial_count: 2, citations: [] },
        { phase: "Phase 2", citations: [] },
        { phase: null as never, trial_count: null as never, citations: [] },
      ],
    });
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("draws one line per series for a grouped time series", () => {
    const grouped: Visualization = {
      ...TIME_SERIES,
      encoding: {
        ...TIME_SERIES.encoding,
        series: { field: "series", type: "nominal", title: "Series" },
      },
      data: [
        { year: "2020", series: "Ozempic", trial_count: 3, citations: [] },
        { year: "2020", series: "Wegovy", trial_count: 1, citations: [] },
        { year: "2021", series: "Ozempic", trial_count: 4, citations: [] },
        { year: "2021", series: "Wegovy", trial_count: 2, citations: [] },
      ],
    };
    const { container } = draw(grouped);
    expect(container.querySelectorAll(".recharts-line").length).toBe(2);
  });

  it("draws one bar group per series for a grouped bar chart", () => {
    const { container } = draw(GROUPED_BAR);
    expect(container.querySelectorAll(".recharts-bar").length).toBe(2);
  });

  it("does not emit a raw long sponsor name into the axis", () => {
    const long = "A National Cooperative Oncology Research Consortium of Somewhere";
    draw({
      ...BAR_CHART,
      encoding: {
        x: { field: "sponsor", type: "nominal", title: "Lead Sponsor" },
        y: { field: "trial_count", type: "quantitative", title: "Number of Trials" },
      },
      data: [{ sponsor: long, trial_count: 3, citations: [] }],
    });
    expect(screen.queryByText(long)).not.toBeInTheDocument();
  });
});

describe("scatter axis safety", () => {
  const axisFor = (visualization: Visualization) => {
    const { container } = draw(visualization);
    return [...container.querySelectorAll(".recharts-yAxis .recharts-cartesian-axis-tick-value")]
      .map((node) => node.textContent ?? "")
      .join(",");
  };

  it("keeps a zero-enrollment study visible by avoiding a log axis", () => {
    // A log scale silently drops 0, and "0 enrolled" is a real reported value.
    expect(axisFor(SCATTER)).toContain("0");
  });

  it("still renders when every value is positive", () => {
    const positive: Visualization = {
      ...SCATTER,
      data: SCATTER.data.map((d, i) => ({ ...d, enrollment: 100 * (i + 1) })),
    };
    expect(axisFor(positive)).not.toBe("");
  });
});

describe("interaction", () => {
  it("hands the clicked datum, with its citations, to the caller", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const { container } = draw(BAR_CHART, onSelect);

    const bar = container.querySelector(".recharts-bar-rectangle path");
    expect(bar).toBeTruthy();
    await user.click(bar as Element);

    expect(onSelect).toHaveBeenCalledTimes(1);
    const datum = onSelect.mock.calls[0][0];
    expect(datum.citations[0].nct_id).toBe("NCT00000001");
  });

  it("hands the clicked network edge to the caller", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const { container } = draw(NETWORK, onSelect);

    const edge = container.querySelector("line");
    expect(edge).toBeTruthy();
    await user.click(edge as Element);

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ source: "Merck", target: "Pembrolizumab", weight: 2 }),
    );
  });

  it("labels network nodes and exposes an accessible description", () => {
    draw(NETWORK);
    expect(screen.getByRole("img", { name: /network of 2 entities/i })).toBeInTheDocument();
    expect(screen.getByText("Merck")).toBeInTheDocument();
    expect(screen.getByText("Pembrolizumab")).toBeInTheDocument();
  });
});

describe("unknown types", () => {
  it("renders an explanation rather than throwing", () => {
    draw({ ...BAR_CHART, type: "sankey" as never });
    expect(screen.getByText(/no renderer is registered for/i)).toBeInTheDocument();
  });
});
