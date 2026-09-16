/**
 * Behavioural tests for the app shell.
 *
 * The network is always a mock, so these assert contract and interaction rather
 * than connectivity: what is (and is not) sent, what survives a race, and what
 * the user is shown when things go wrong.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { BAR_CHART, NETWORK, responseFor } from "./test/fixtures";

const ok = (body: unknown) =>
  ({ ok: true, status: 200, json: async () => body }) as unknown as Response;
const fail = (status: number, body: unknown) =>
  ({ ok: false, status, json: async () => body }) as unknown as Response;

/** Routes /examples to a stub and hands every /analyze call to `analyze`. */
function mockFetch(analyze: (body: any) => Promise<Response> | Response) {
  const spy = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith("/examples")) return ok([]);
    return analyze(init?.body ? JSON.parse(String(init.body)) : {});
  });
  vi.stubGlobal("fetch", spy as unknown as typeof fetch);
  return spy;
}

/** Only the POSTs to /analyze, ignoring the examples bootstrap. */
const analyzeCalls = (spy: ReturnType<typeof mockFetch>) =>
  spy.mock.calls.filter(([url]) => String(url).endsWith("/analyze"));

const analyzeBodies = (spy: ReturnType<typeof mockFetch>) =>
  analyzeCalls(spy).map(([, init]: any) => JSON.parse(init.body));

const input = () => screen.getByLabelText(/your question about clinical trials/i);
const runButton = () => screen.getByRole("button", { name: /^run/i });

beforeEach(() => {
  localStorage.clear();
});

// ---------------------------------------------------------------------------
// Empty-query guard
// ---------------------------------------------------------------------------

describe("empty query", () => {
  it("does not call the API and shows an inline error", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.click(runButton());

    expect(await screen.findByText("Please enter a question")).toBeInTheDocument();
    expect(analyzeCalls(spy)).toHaveLength(0);
  });

  it("does not call the API for a whitespace-only query", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.type(input(), "   ");
    await user.click(runButton());

    expect(await screen.findByText("Please enter a question")).toBeInTheDocument();
    expect(analyzeCalls(spy)).toHaveLength(0);
  });

  it("shows no loading state and records no recent query", async () => {
    const user = userEvent.setup();
    mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.type(input(), " \n ");
    await user.click(runButton());

    expect(screen.queryByText(/analyzing clinical trials/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^recent$/i)).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("ctgov.recentQueries") ?? "[]")).toEqual([]);
    // The empty state survives: the UI is not torn down by a failed submit.
    expect(screen.getByText(/ask a question about clinical trials/i)).toBeInTheDocument();
  });

  it("clears the inline error as soon as the user types", async () => {
    const user = userEvent.setup();
    mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.click(runButton());
    expect(await screen.findByText("Please enter a question")).toBeInTheDocument();

    await user.type(input(), "melanoma");
    expect(screen.queryByText("Please enter a question")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Intent chips
// ---------------------------------------------------------------------------

describe("intent chips", () => {
  it("never overwrites a query the user typed", async () => {
    const user = userEvent.setup();
    mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    const custom = "How many oncology trials started in California since 2020?";
    await user.type(input(), custom);
    await user.click(screen.getByRole("button", { name: "Time Trend" }));

    expect(input()).toHaveValue(custom);
  });

  it("keeps the query stable across repeated chip changes", async () => {
    const user = userEvent.setup();
    mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    const custom = "How many oncology trials started in California since 2020?";
    await user.type(input(), custom);
    for (const label of ["Time Trend", "Geography", "Network", "Correlation"]) {
      await user.click(screen.getByRole("button", { name: label }));
      expect(input()).toHaveValue(custom);
    }
    expect(screen.getByRole("button", { name: "Correlation" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("fills in the example query only when the input is empty", async () => {
    const user = userEvent.setup();
    mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Network" }));
    expect(input()).toHaveValue("Show a network of sponsors and drugs for diabetes trials");
  });

  it("sends the hint alongside the untouched query", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    const custom = "How many oncology trials started in California since 2020?";
    await user.type(input(), custom);
    await user.click(screen.getByRole("button", { name: "Time Trend" }));
    await user.click(runButton());

    await waitFor(() => expect(analyzeBodies(spy)).toHaveLength(1));
    expect(analyzeBodies(spy)[0]).toEqual({ query: custom, intent_hint: "time_trend" });
  });

  it("omits intent_hint entirely when no chip is selected", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.type(input(), "breast cancer trials by phase");
    await user.click(runButton());

    await waitFor(() => expect(analyzeBodies(spy)).toHaveLength(1));
    expect(analyzeBodies(spy)[0]).toEqual({ query: "breast cancer trials by phase" });
  });

  it("toggles the active chip off when clicked again", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.type(input(), "melanoma trials");
    const chip = screen.getByRole("button", { name: "Geography" });

    await user.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "true");
    await user.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "false");

    await user.click(runButton());
    await waitFor(() => expect(analyzeBodies(spy)).toHaveLength(1));
    expect(analyzeBodies(spy)[0].intent_hint).toBeUndefined();
  });

  it("does not run the query just because a chip was clicked", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Distribution" }));
    expect(analyzeCalls(spy)).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Brand → generic expansion
// ---------------------------------------------------------------------------

describe("drug synonym expansion", () => {
  it("expands the outbound query but leaves the input and history untouched", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.type(input(), "How many Keytruda trials are there?");
    await user.click(runButton());

    await waitFor(() => expect(analyzeBodies(spy)).toHaveLength(1));
    expect(analyzeBodies(spy)[0].query).toBe(
      "How many Keytruda (Pembrolizumab) trials are there?",
    );
    expect(input()).toHaveValue("How many Keytruda trials are there?");

    const recent = JSON.parse(localStorage.getItem("ctgov.recentQueries")!);
    expect(recent[0].query).toBe("How many Keytruda trials are there?");
  });

  it("never double-expands when the same query is run repeatedly", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.type(input(), "Keytruda trials");
    await user.click(runButton());
    await waitFor(() => expect(analyzeBodies(spy)).toHaveLength(1));
    await user.click(runButton());
    await waitFor(() => expect(analyzeBodies(spy)).toHaveLength(2));

    for (const body of analyzeBodies(spy)) {
      expect(body.query).toBe("Keytruda (Pembrolizumab) trials");
    }
  });
});

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

describe("error states", () => {
  const noMatch = {
    error: {
      code: "NO_MATCHING_TRIALS",
      message: "No ClinicalTrials.gov studies matched the supplied query and filters.",
      details: { search_terms: ["zzzz"] },
      request_id: "abc123def456",
    },
  };

  async function submit(body: unknown, status = 404) {
    const user = userEvent.setup();
    mockFetch(() => fail(status, body));
    render(<App />);
    await user.type(input(), "trials for zzzz");
    await user.click(runButton());
  }

  it("renders a friendly card for NO_MATCHING_TRIALS", async () => {
    await submit(noMatch);

    expect(await screen.findByText("No results found")).toBeInTheDocument();
    expect(
      screen.getByText("Try rephrasing your question or using a different drug/condition name"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Request ID: abc123def456/)).toBeInTheDocument();
  });

  it("does not dump raw JSON into the main UI", async () => {
    await submit(noMatch);
    await screen.findByText("No results found");

    const alert = screen.getByRole("alert");
    // The structured payload is only reachable behind the collapsed disclosure.
    expect(within(alert).getByText(/technical details/i).closest("details")).toBeTruthy();
    const visible = alert.textContent ?? "";
    expect(visible.indexOf("No results found")).toBeLessThan(visible.indexOf("search_terms"));
  });

  it("renders without a request id when the backend omits one", async () => {
    await submit({ error: { ...noMatch.error, request_id: null } });

    expect(await screen.findByText("No results found")).toBeInTheDocument();
    expect(screen.queryByText(/Request ID:/)).not.toBeInTheDocument();
  });

  it("survives a malformed error body", async () => {
    await submit({ unexpected: "shape" }, 500);

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("explains a generic backend failure without a stack trace", async () => {
    await submit(
      {
        error: {
          code: "CTGOV_UNAVAILABLE",
          message: "ClinicalTrials.gov request failed",
          details: {},
          request_id: "req-9",
        },
      },
      502,
    );

    expect(await screen.findByText("ClinicalTrials.gov is unavailable")).toBeInTheDocument();
    expect(screen.getByText(/Request ID: req-9/)).toBeInTheDocument();
  });

  it("explains a network failure in plain language", async () => {
    const user = userEvent.setup();
    mockFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    render(<App />);

    await user.type(input(), "melanoma trials");
    await user.click(runButton());

    expect(await screen.findByText("Cannot reach the service")).toBeInTheDocument();
  });

  it("stops showing the loading state after a failure", async () => {
    await submit(noMatch);
    await screen.findByText("No results found");
    expect(screen.queryByText(/analyzing clinical trials/i)).not.toBeInTheDocument();
    expect(runButton()).toBeEnabled();
  });
});

// ---------------------------------------------------------------------------
// Concurrency
// ---------------------------------------------------------------------------

describe("concurrent requests", () => {
  it("shows the newest result even when an earlier request resolves later", async () => {
    const user = userEvent.setup();
    const slow: { release?: (value: Response) => void } = {};

    mockFetch((body) => {
      if (body.query.includes("slow")) {
        return new Promise<Response>((resolve) => {
          slow.release = resolve;
        });
      }
      return ok(responseFor({ ...BAR_CHART, title: "Fast result" }));
    });

    render(<App />);

    // Seed the history so there is a second, still-clickable way to submit
    // while a request is in flight (the Run button is disabled during loading).
    await user.type(input(), "fast seed query");
    await user.click(runButton());
    await screen.findByText("Fast result");

    await user.clear(input());
    await user.type(input(), "slow query");
    await user.click(runButton());
    expect(await screen.findByText(/analyzing clinical trials/i)).toBeInTheDocument();

    // Supersede the slow request with a fast one.
    await user.click(screen.getByRole("button", { name: "fast seed query" }));
    expect(await screen.findByText("Fast result")).toBeInTheDocument();

    // The stale request now answers — it must not replace the newer result.
    slow.release?.(ok(responseFor({ ...BAR_CHART, title: "Stale result" })));
    await new Promise((resolve) => setTimeout(resolve, 30));

    expect(screen.getByText("Fast result")).toBeInTheDocument();
    expect(screen.queryByText("Stale result")).not.toBeInTheDocument();
  });

  it("disables Run while a request is in flight so it cannot be double-submitted", async () => {
    const user = userEvent.setup();
    mockFetch(() => new Promise<Response>(() => {}));
    render(<App />);

    await user.type(input(), "melanoma trials");
    await user.click(runButton());

    expect(await screen.findByText(/analyzing clinical trials/i)).toBeInTheDocument();
    expect(runButton()).toBeDisabled();
  });

  it("survives rapid repeated Run clicks and always settles", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.type(input(), "melanoma trials");
    const button = runButton();
    await user.click(button);
    await user.click(button);
    await user.click(button);

    expect(await screen.findByText(BAR_CHART.title)).toBeInTheDocument();
    await waitFor(() => expect(runButton()).toBeEnabled());
    expect(analyzeCalls(spy).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Recent queries
// ---------------------------------------------------------------------------

describe("recent queries", () => {
  it("keeps at most five, newest first, without duplicates", async () => {
    const user = userEvent.setup();
    mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    for (const term of ["one", "two", "three", "four", "five", "six", "two"]) {
      await user.clear(input());
      await user.type(input(), `${term} trials`);
      await user.click(runButton());
      await screen.findByText(BAR_CHART.title);
    }

    const stored = JSON.parse(localStorage.getItem("ctgov.recentQueries")!);
    expect(stored).toHaveLength(5);
    expect(stored[0].query).toBe("two trials");
    expect(new Set(stored.map((s: any) => s.query)).size).toBe(5);
    expect(stored.map((s: any) => s.query)).not.toContain("one trials");
  });

  it("re-runs the original query text when a recent pill is clicked", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.type(input(), "melanoma trials by phase");
    await user.click(runButton());
    await screen.findByText(BAR_CHART.title);

    await user.clear(input());
    await user.click(screen.getByRole("button", { name: "melanoma trials by phase" }));

    await waitFor(() => expect(analyzeBodies(spy)).toHaveLength(2));
    expect(analyzeBodies(spy)[1].query).toBe("melanoma trials by phase");
    expect(input()).toHaveValue("melanoma trials by phase");
  });

  it("restores the hint that was used for that query", async () => {
    const user = userEvent.setup();
    const spy = mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.type(input(), "melanoma trials");
    await user.click(screen.getByRole("button", { name: "Geography" }));
    await user.click(runButton());
    await screen.findByText(BAR_CHART.title);

    await user.click(screen.getByRole("button", { name: "Geography" })); // clear the chip
    await user.click(screen.getByRole("button", { name: "melanoma trials" }));

    await waitFor(() => expect(analyzeBodies(spy)).toHaveLength(2));
    expect(analyzeBodies(spy)[1].intent_hint).toBe("geographic");
  });

  it("ignores corrupt persisted history rather than crashing", async () => {
    localStorage.setItem("ctgov.recentQueries", "{not json");
    mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);
    expect(screen.getByText(/ask a question about clinical trials/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Successful render
// ---------------------------------------------------------------------------

describe("results", () => {
  it("renders the interpretation, chart card and citation prompt", async () => {
    const user = userEvent.setup();
    mockFetch(() => ok(responseFor(BAR_CHART)));
    render(<App />);

    await user.type(input(), "melanoma by phase");
    await user.click(runButton());

    expect(await screen.findByText(BAR_CHART.title)).toBeInTheDocument();
    expect(screen.getByText("Interpretation")).toBeInTheDocument();
    expect(screen.getAllByText("Distribution").length).toBeGreaterThan(0);
    expect(screen.getByText("Source traceability")).toBeInTheDocument();
    expect(screen.getByText(/click any bar, point or edge/i)).toBeInTheDocument();
  });

  it("discloses a truncated result set in the methodology panel", async () => {
    const user = userEvent.setup();
    mockFetch(() =>
      ok(
        responseFor({
          ...BAR_CHART,
          metadata: { ...BAR_CHART.metadata, truncated: true, studies_available: 12000 },
        }),
      ),
    );
    render(<App />);

    await user.type(input(), "cancer");
    await user.click(runButton());

    expect(await screen.findByText("No — capped sample")).toBeInTheDocument();
    expect(screen.getByText("12,000")).toBeInTheDocument();
  });

  it("renders a network response without a cartesian encoding", async () => {
    const user = userEvent.setup();
    mockFetch(() => ok(responseFor(NETWORK, { intent: "relationship" })));
    render(<App />);

    await user.type(input(), "sponsor drug network for diabetes");
    await user.click(runButton());

    expect(await screen.findByText(NETWORK.title)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /network of 2 entities/i })).toBeInTheDocument();
  });

  it("reports an unknown visualization type instead of crashing", async () => {
    const user = userEvent.setup();
    mockFetch(() =>
      ok(responseFor({ ...BAR_CHART, type: "pie_chart" as never })),
    );
    render(<App />);

    await user.type(input(), "melanoma");
    await user.click(runButton());

    expect(await screen.findByText(/no renderer is registered for/i)).toBeInTheDocument();
  });

  it("rejects a response body that is not a visualization", async () => {
    const user = userEvent.setup();
    mockFetch(() => ok({ something: "else" }));
    render(<App />);

    await user.type(input(), "melanoma");
    await user.click(runButton());

    expect(await screen.findByText("Unexpected response")).toBeInTheDocument();
  });
});
