/**
 * End-to-end test against a *running backend* and the live ClinicalTrials.gov
 * API — no mocks anywhere. Opt-in, because it needs the network and a server:
 *
 *   # terminal 1
 *   cd backend && uvicorn app.main:app --port 8000
 *   # terminal 2
 *   cd frontend && VITE_API_BASE=http://127.0.0.1:8000 npm test
 *
 * Setting VITE_API_BASE is what switches these on: without it there is nothing
 * to point at, so the block is skipped.
 *
 * It exists because the mocked suite can only prove the frontend handles the
 * shapes we *think* the backend returns. This proves it handles the shapes it
 * actually returns.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import App from "./App";

// The API client resolves its base URL at module load, so VITE_API_BASE has to
// be set in the environment before vitest starts, not from inside a test — which
// makes its presence the natural switch for this block.
const API = import.meta.env.VITE_API_BASE;
const LIVE = Boolean(API);
const describeLive = LIVE ? describe : describe.skip;

beforeAll(() => {
  if (!LIVE) return;

  // Environment workaround, not a behaviour change: Node's fetch rejects
  // jsdom's AbortSignal ("Expected signal to be an instance of AbortSignal"),
  // which no real browser does. Drop the signal for live runs only; request
  // cancellation itself is covered by the mocked suite.
  const nativeFetch = globalThis.fetch;
  vi.stubGlobal("fetch", (url: RequestInfo | URL, init: RequestInit = {}) => {
    const { signal: _dropped, ...rest } = init;
    return nativeFetch(url, rest);
  });
});

const input = () => screen.getByLabelText(/your question about clinical trials/i);
const runButton = () => screen.getByRole("button", { name: /^run/i });

async function ask(query: string) {
  const user = userEvent.setup();
  render(<App />);
  await user.type(input(), query);
  await user.click(runButton());
  await waitFor(
    () => expect(screen.queryByText(/analyzing clinical trials/i)).not.toBeInTheDocument(),
    { timeout: 120_000 },
  );
}

describeLive("live backend", () => {
  it("reaches a healthy backend", async () => {
    const health = await fetch(`${API}/health`).then((r) => r.json());
    expect(health.status).toBe("ok");
  });

  it.each([
    ["How has the number of trials for Pembrolizumab changed per year since 2015?", "time series"],
    ["How are breast cancer trials distributed across phases?", "bar chart"],
    ["Compare trial counts by phase for Ozempic vs Wegovy", "grouped bar chart"],
    ["Which countries have the most recruiting trials for Alzheimer's disease?", "bar chart"],
    ["Show a network of sponsors and drugs for diabetes trials", "network graph"],
    ["Is there a relationship between enrollment and start year for melanoma trials?", "scatter plot"],
  ])("renders a real response for %s", async (query, expectedCardTitle) => {
    await ask(query);

    expect(screen.getByText("Interpretation")).toBeInTheDocument();
    expect(screen.getByText(expectedCardTitle)).toBeInTheDocument();
    expect(screen.getByText("Source traceability")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  }, 180_000);

  it("shows the friendly no-results card for an unmatchable question", async () => {
    await ask("trials for zzzzqqqxyz nonexistent condition");
    expect(await screen.findByText("No results found")).toBeInTheDocument();
    expect(screen.getByText(/Request ID:/)).toBeInTheDocument();
  }, 120_000);
});
