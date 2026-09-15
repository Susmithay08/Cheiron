/** Loading, error and empty states. */

import type { ApiError } from "../types/api";

const FRIENDLY: Record<string, string> = {
  NO_MATCHING_TRIALS: "No studies matched",
  CTGOV_UNAVAILABLE: "ClinicalTrials.gov is unavailable",
  CTGOV_BAD_QUERY: "ClinicalTrials.gov rejected the query",
  INSUFFICIENT_FIELD_COVERAGE: "Not enough reported data",
  INSUFFICIENT_RELATIONSHIPS: "Not enough linked entities",
  INVALID_REQUEST: "The request was not valid",
  NETWORK_ERROR: "Cannot reach the service",
};

export function LoadingState({ query }: { query: string }) {
  const steps = [
    "Planning the query",
    "Retrieving ClinicalTrials.gov studies",
    "Aggregating and tracing sources",
  ];
  return (
    <div className="flex h-96 flex-col items-center justify-center gap-4 rounded-xl border border-slate-200 bg-white">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
      <p className="max-w-md text-center text-sm text-slate-500">“{query}”</p>
      <ul className="space-y-1 text-xs text-slate-400">
        {steps.map((step) => (
          <li key={step}>{step}…</li>
        ))}
      </ul>
    </div>
  );
}

export function ErrorState({ error }: { error: ApiError }) {
  const details = Object.entries(error.details ?? {});
  return (
    <div className="rounded-xl border border-red-200 bg-red-50/60 p-6">
      <div className="flex items-center gap-2">
        <span className="rounded-md bg-red-100 px-2 py-0.5 font-mono text-xs text-red-700">
          {error.code}
        </span>
        <h2 className="font-semibold text-red-900">{FRIENDLY[error.code] ?? "Request failed"}</h2>
      </div>
      <p className="mt-2 text-sm text-red-800">{error.message}</p>
      {details.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-medium text-red-700">Details</summary>
          <pre className="mt-2 overflow-x-auto rounded-lg bg-white/70 p-3 text-xs text-red-900">
            {JSON.stringify(error.details, null, 2)}
          </pre>
        </details>
      )}
      {error.request_id && (
        <p className="mt-3 font-mono text-xs text-red-400">request {error.request_id}</p>
      )}
    </div>
  );
}

export function EmptyState() {
  return (
    <div className="flex h-96 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-slate-300 bg-white/50 text-center">
      <p className="text-lg font-medium text-slate-700">Ask a question about clinical trials</p>
      <p className="max-w-md text-sm text-slate-500">
        Every answer is a chart built from live ClinicalTrials.gov records, and every data
        point links back to the studies that produced it. Try one of the examples above.
      </p>
    </div>
  );
}
