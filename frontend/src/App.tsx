import { useEffect, useState } from "react";

import { analyze, AnalyzeError, fetchExamples } from "./api/client";
import { VisualizationRenderer } from "./charts/VisualizationRenderer";
import { CitationPanel, Card, InterpretationPanel, MethodologyPanel } from "./components/Panels";
import { EmptyState, ErrorState, LoadingState } from "./components/States";
import type { AnalyzeResponse, ApiError, Datum, ExampleQuery } from "./types/api";

const FALLBACK_EXAMPLES: ExampleQuery[] = [
  { label: "Time trend", query: "How has the number of trials for Pembrolizumab changed per year since 2015?", intent: "time_trend" },
  { label: "Distribution", query: "How are breast cancer trials distributed across phases?", intent: "distribution" },
  { label: "Comparison", query: "Compare trial counts by phase for Ozempic vs Wegovy", intent: "comparison" },
  { label: "Geography", query: "Which countries have the most recruiting trials for Alzheimer's disease?", intent: "geographic" },
  { label: "Network", query: "Show a network of sponsors and drugs for diabetes trials", intent: "relationship" },
  { label: "Correlation", query: "Is there a relationship between enrollment and start year for melanoma trials?", intent: "correlation" },
];

/** Label used in the citation panel header for the selected datum. */
function labelFor(datum: Datum, response: AnalyzeResponse): string {
  const viz = response.visualization;
  if (viz.type === "network_graph") return `${datum.source} ↔ ${datum.target}`;
  const x = viz.encoding.x?.field;
  const y = viz.encoding.y?.field;
  const series = datum.series ? ` (${datum.series})` : "";
  if (viz.type === "scatter_plot") return String(datum.nct_id);
  return `${String(datum[x!])}${series} = ${String(datum[y!])}`;
}

export default function App() {
  const [query, setQuery] = useState("");
  const [examples, setExamples] = useState<ExampleQuery[]>(FALLBACK_EXAMPLES);
  const [response, setResponse] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState("");
  const [selected, setSelected] = useState<Datum | null>(null);
  const [history, setHistory] = useState<string[]>([]);

  useEffect(() => {
    fetchExamples().then((fetched) => fetched.length && setExamples(fetched));
  }, []);

  async function run(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setPending(trimmed);
    setError(null);
    setSelected(null);
    try {
      const result = await analyze(trimmed);
      setResponse(result);
      setHistory((previous) => [trimmed, ...previous.filter((q) => q !== trimmed)].slice(0, 6));
    } catch (exception) {
      setResponse(null);
      setError(
        exception instanceof AnalyzeError
          ? exception.detail
          : { code: "UNKNOWN_ERROR", message: String(exception), details: {} },
      );
    } finally {
      setLoading(false);
    }
  }

  const viz = response?.visualization;
  const selectedKey =
    selected && viz?.encoding.x
      ? `${String(selected[viz.encoding.x.field])}::${String(selected.series ?? "")}`
      : null;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-5">
          <div className="flex items-baseline gap-3">
            <h1 className="text-xl font-semibold tracking-tight">ClinicalTrials Intelligence</h1>
            <span className="text-sm text-slate-400">query → visualization, with sources</span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-5 px-6 py-6">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run(query);
          }}
          className="flex flex-col gap-3 sm:flex-row"
        >
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="How has the number of trials for Pembrolizumab changed since 2015?"
            maxLength={500}
            className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="rounded-lg bg-slate-900 px-6 py-3 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {loading ? "Running…" : "Run"}
          </button>
        </form>

        <div className="flex flex-wrap gap-2">
          {examples.map((example) => (
            <button
              key={example.label}
              onClick={() => {
                setQuery(example.query);
                void run(example.query);
              }}
              disabled={loading}
              className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-medium text-slate-600 transition hover:border-slate-400 hover:text-slate-900 disabled:opacity-50"
            >
              {example.label}
            </button>
          ))}
        </div>

        {history.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span>Recent:</span>
            {history.map((item) => (
              <button
                key={item}
                onClick={() => {
                  setQuery(item);
                  void run(item);
                }}
                className="max-w-xs truncate rounded px-2 py-1 hover:bg-slate-200 hover:text-slate-700"
              >
                {item}
              </button>
            ))}
          </div>
        )}

        {loading && <LoadingState query={pending} />}
        {!loading && error && <ErrorState error={error} />}
        {!loading && !error && !response && <EmptyState />}

        {!loading && response && viz && (
          <div className="space-y-5">
            <InterpretationPanel response={response} />

            <Card
              title={viz.type.replace(/_/g, " ")}
              right={
                <span className="text-xs text-slate-400">
                  {viz.metadata.studies_matched.toLocaleString()} studies
                </span>
              }
            >
              <h3 className="text-lg font-semibold text-slate-900">{viz.title}</h3>
              {viz.description && <p className="mt-1 text-sm text-slate-500">{viz.description}</p>}
              <div className="mt-4 h-[520px] w-full">
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

      <footer className="mx-auto max-w-6xl px-6 pb-10 text-xs text-slate-400">
        Data from ClinicalTrials.gov API v2. The language model plans the query; every number
        shown is computed from retrieved study records.
      </footer>
    </div>
  );
}
