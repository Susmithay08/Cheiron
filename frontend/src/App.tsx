import { useCallback, useEffect, useRef, useState } from "react";

import { analyze, AnalyzeError, fetchExamples } from "./api/client";
import { VisualizationRenderer } from "./charts/VisualizationRenderer";
import {
  Card,
  CitationPanel,
  INTENT_LABELS,
  IntentBadge,
  InterpretationPanel,
  MethodologyPanel,
} from "./components/Panels";
import { EmptyState, ErrorState, LoadingState } from "./components/States";
import { expandBrandNames } from "./lib/synonyms";
import type {
  AnalyzeResponse,
  ApiError,
  Datum,
  ExampleQuery,
  IntentHint,
} from "./types/api";

/** Used until GET /examples answers, and as the chip → example-query mapping. */
const FALLBACK_EXAMPLES: ExampleQuery[] = [
  { label: "Time Trend", query: "How has the number of trials for Pembrolizumab changed per year since 2015?", intent: "time_trend" },
  { label: "Distribution", query: "How are breast cancer trials distributed across phases?", intent: "distribution" },
  { label: "Comparison", query: "Compare trial counts by phase for Ozempic vs Wegovy", intent: "comparison" },
  { label: "Geography", query: "Which countries have the most recruiting trials for Alzheimer's disease?", intent: "geographic" },
  { label: "Network", query: "Show a network of sponsors and drugs for diabetes trials", intent: "relationship" },
  { label: "Correlation", query: "Is there a relationship between enrollment and start year for melanoma trials?", intent: "correlation" },
];

/** Chip order is fixed so the row does not reshuffle when /examples arrives. */
const CHIP_ORDER: IntentHint[] = [
  "time_trend",
  "distribution",
  "comparison",
  "geographic",
  "relationship",
  "correlation",
];

const HISTORY_KEY = "ctgov.recentQueries";
const HISTORY_LIMIT = 5;

interface RecentQuery {
  query: string;
  hint: IntentHint | null;
}

function loadHistory(): RecentQuery[] {
  try {
    const raw = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]");
    if (!Array.isArray(raw)) return [];
    return raw
      .filter((item): item is RecentQuery => typeof item?.query === "string")
      .slice(0, HISTORY_LIMIT);
  } catch {
    return [];
  }
}

/** Label used in the citation panel header for the selected datum. */
function labelFor(datum: Datum, response: AnalyzeResponse): string {
  const viz = response.visualization;
  if (viz.type === "network_graph") return `${datum.source} ↔ ${datum.target}`;
  if (viz.type === "scatter_plot") return String(datum.nct_id);
  const x = viz.encoding.x?.field;
  const y = viz.encoding.y?.field;
  const series = datum.series ? ` (${datum.series})` : "";
  if (!x || !y) return "this data point";
  return `${String(datum[x])}${series} = ${String(datum[y])}`;
}

export default function App() {
  const [query, setQuery] = useState("");
  const [hint, setHint] = useState<IntentHint | null>(null);
  const [examples, setExamples] = useState<ExampleQuery[]>(FALLBACK_EXAMPLES);
  const [response, setResponse] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [inputError, setInputError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState("");
  const [selected, setSelected] = useState<Datum | null>(null);
  const [history, setHistory] = useState<RecentQuery[]>(loadHistory);

  // Monotonic request id: a response is applied only if it belongs to the most
  // recent request, so a slow early request can never overwrite a fast later one.
  const latestRequest = useRef(0);
  const inFlight = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetchExamples().then((fetched) => fetched.length && setExamples(fetched));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    } catch {
      /* storage may be unavailable (private mode); history is a convenience only */
    }
  }, [history]);

  const run = useCallback(
    async (text: string, intentHint: IntentHint | null) => {
      const trimmed = text.trim();

      // Bug guard: an empty or whitespace-only question never reaches the network.
      if (!trimmed) {
        setInputError("Please enter a question");
        setLoading(false);
        inputRef.current?.focus();
        return;
      }
      setInputError(null);

      // Supersede anything still running rather than racing it.
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      const requestNumber = ++latestRequest.current;

      setLoading(true);
      setPending(trimmed);
      setError(null);
      setSelected(null);

      try {
        const result = await analyze(
          {
            // The brand→generic expansion applies to the outbound query only;
            // the user's own wording is what is displayed and remembered.
            query: expandBrandNames(trimmed),
            ...(intentHint ? { intent_hint: intentHint } : {}),
          },
          controller.signal,
        );
        if (requestNumber !== latestRequest.current) return; // stale
        setResponse(result);
        setHistory((previous) =>
          [
            { query: trimmed, hint: intentHint },
            ...previous.filter((item) => item.query !== trimmed),
          ].slice(0, HISTORY_LIMIT),
        );
      } catch (exception) {
        if ((exception as Error)?.name === "AbortError") return;
        if (requestNumber !== latestRequest.current) return; // stale
        setResponse(null);
        setError(
          exception instanceof AnalyzeError
            ? exception.detail
            : {
                code: "UNKNOWN_ERROR",
                message: String((exception as Error)?.message ?? exception),
                details: {},
                request_id: null,
              },
        );
      } finally {
        if (requestNumber === latestRequest.current) setLoading(false);
      }
    },
    [],
  );

  /**
   * A chip selects an *analysis type*, it does not rewrite the question.
   * The one exception is an empty input, where the chip's example query is a
   * useful way in — that is onboarding, not substitution.
   */
  function onChipClick(intent: IntentHint) {
    const next = hint === intent ? null : intent;
    setHint(next);
    if (!query.trim()) {
      const example = examples.find((e) => e.intent === intent);
      if (example) {
        setQuery(example.query);
        setInputError(null);
      }
    }
  }

  const viz = response?.visualization;
  const selectedKey =
    selected && viz?.encoding.x
      ? `${String(selected[viz.encoding.x.field])}::${String(selected.series ?? "")}`
      : null;

  const chips = CHIP_ORDER.map((intent) => ({
    intent,
    label:
      examples.find((e) => e.intent === intent)?.label ?? INTENT_LABELS[intent] ?? intent,
  }));

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="border-b border-edge bg-card/40">
        <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6">
          <h1 className="text-2xl font-bold tracking-tight text-white">
            ClinicalTrials Intelligence
          </h1>
          <p className="mt-0.5 text-sm text-brand-bright">query → visualization, with sources</p>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run(query, hint);
          }}
          className="space-y-3"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch">
            <div className="flex-1">
              <label htmlFor="query" className="sr-only">
                Your question about clinical trials
              </label>
              <textarea
                id="query"
                ref={inputRef}
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  if (inputError) setInputError(null);
                }}
                onKeyDown={(event) => {
                  // Enter submits; Shift+Enter keeps the newline.
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void run(query, hint);
                  }
                }}
                rows={2}
                placeholder="How has the number of trials for Pembrolizumab changed since 2015?"
                maxLength={500}
                aria-invalid={Boolean(inputError)}
                aria-describedby={inputError ? "query-error" : undefined}
                className="w-full resize-y rounded-control border bg-card px-4 py-3 text-sm text-ink placeholder:text-muted/70 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/40"
                style={{ borderColor: inputError ? "var(--color-danger)" : "var(--color-edge)" }}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="h-fit rounded-control bg-gradient-to-br from-brand to-brand-bright px-7 py-3 text-sm font-semibold text-white shadow-card transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50 sm:self-start"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                  Running…
                </span>
              ) : (
                "Run"
              )}
            </button>
          </div>

          {inputError && (
            <p id="query-error" role="alert" className="text-sm font-medium text-danger">
              {inputError}
            </p>
          )}

          <div
            className="flex flex-wrap gap-2"
            role="group"
            aria-label="Preferred analysis type"
          >
            {chips.map(({ intent, label }) => {
              const active = hint === intent;
              return (
                <button
                  key={intent}
                  type="button"
                  aria-pressed={active}
                  onClick={() => onChipClick(intent)}
                  className={`rounded-control border px-3.5 py-1.5 text-xs font-medium transition ${
                    active
                      ? "border-brand-bright bg-brand/20 text-ink shadow-glow"
                      : "border-brand-deep bg-card text-brand-soft hover:border-brand-bright hover:text-ink"
                  }`}
                >
                  {label}
                </button>
              );
            })}
            {hint && (
              <button
                type="button"
                onClick={() => setHint(null)}
                className="rounded-control px-2.5 py-1.5 text-xs text-muted transition hover:text-ink"
              >
                Clear
              </button>
            )}
          </div>
        </form>

        {history.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="uppercase tracking-wider">Recent</span>
            {history.map((item) => (
              <button
                key={item.query}
                type="button"
                title={item.query}
                onClick={() => {
                  setQuery(item.query);
                  setHint(item.hint);
                  void run(item.query, item.hint);
                }}
                className="max-w-[16rem] truncate rounded-control border border-edge bg-card px-2.5 py-1 text-muted transition hover:border-brand hover:text-ink"
              >
                {item.query}
              </button>
            ))}
          </div>
        )}

        {loading && <LoadingState query={pending} />}
        {!loading && error && <ErrorState error={error} />}
        {!loading && !error && !response && (
          <EmptyState
            examples={examples}
            onPick={(text) => {
              setQuery(text);
              setInputError(null);
              inputRef.current?.focus();
            }}
          />
        )}

        {!loading && !error && response && viz && (
          <div className="space-y-5">
            <InterpretationPanel response={response} />

            <Card
              title={viz.type.replace(/_/g, " ")}
              right={
                <div className="flex items-center gap-2">
                  <IntentBadge intent={response.meta.plan.intent} />
                  <span className="text-xs text-muted">
                    {viz.metadata.studies_matched.toLocaleString()} studies
                  </span>
                </div>
              }
            >
              <h3 className="text-lg font-semibold text-ink">{viz.title}</h3>
              {viz.description && <p className="mt-1 text-sm text-muted">{viz.description}</p>}
              <div className="mt-4 h-[420px] w-full sm:h-[520px]">
                <VisualizationRenderer
                  visualization={viz}
                  onSelect={setSelected}
                  selectedKey={selectedKey}
                />
              </div>
            </Card>

            <div className="grid gap-5 lg:grid-cols-2">
              <MethodologyPanel visualization={viz} />
              <CitationPanel
                datum={selected}
                label={selected ? labelFor(selected, response) : ""}
                fallbackCount={viz.data.length || (viz.edges?.length ?? 0)}
              />
            </div>
          </div>
        )}
      </main>

      <footer className="mx-auto max-w-6xl px-4 pb-10 text-xs text-muted sm:px-6">
        Data from the ClinicalTrials.gov API v2. The language model plans the query; every number
        shown is computed from retrieved study records.
      </footer>
    </div>
  );
}
