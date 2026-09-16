/** Loading, error and empty states. */

import type { ApiError, ExampleQuery } from "../types/api";

const FRIENDLY: Record<string, { heading: string; message: string }> = {
  NO_MATCHING_TRIALS: {
    heading: "No results found",
    message: "Try rephrasing your question or using a different drug/condition name",
  },
  INSUFFICIENT_FIELD_COVERAGE: {
    heading: "Not enough reported data",
    message:
      "The matching studies do not report the field this chart needs. Try a different question or a broader search.",
  },
  INSUFFICIENT_RELATIONSHIPS: {
    heading: "Not enough linked entities",
    message:
      "These studies do not share enough sponsors or drugs to form a meaningful network. Try a broader condition.",
  },
  CTGOV_UNAVAILABLE: {
    heading: "ClinicalTrials.gov is unavailable",
    message: "The registry did not respond. This is usually temporary — try again in a moment.",
  },
  CTGOV_BAD_QUERY: {
    heading: "ClinicalTrials.gov rejected the search",
    message: "The registry could not interpret this search. Try simpler wording.",
  },
  CTGOV_NOT_FOUND: {
    heading: "ClinicalTrials.gov could not find that",
    message: "The registry has no record at that address.",
  },
  CTGOV_BAD_RESPONSE: {
    heading: "Unreadable response from ClinicalTrials.gov",
    message: "The registry returned something this service could not parse. Try again shortly.",
  },
  NETWORK_ERROR: {
    heading: "Cannot reach the service",
    message: "The analysis service did not respond. Check that the backend is running.",
  },
  INVALID_REQUEST: {
    heading: "That request was not valid",
    message: "Please adjust the question and try again.",
  },
  MALFORMED_RESPONSE: {
    heading: "Unexpected response",
    message: "The service replied with something this page could not render.",
  },
  EMPTY_QUERY: {
    heading: "Please enter a question",
    message: "Type a question about clinical trials, or pick one of the examples.",
  },
};

const FALLBACK = {
  heading: "Something went wrong",
  message: "The request could not be completed. Please try again.",
};

function SearchIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.2-3.2" />
    </svg>
  );
}

function AlertIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d="M12 3.5 2.6 19.5h18.8L12 3.5Z" />
      <path d="M12 10v4" />
      <path d="M12 17.2h.01" />
    </svg>
  );
}

function ChartIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M22 20H2" />
    </svg>
  );
}

export function LoadingState({ query }: { query: string }) {
  return (
    <section
      aria-live="polite"
      aria-busy="true"
      className="rounded-card border border-edge bg-card p-6 shadow-card sm:p-8"
    >
      <div className="flex items-center gap-3">
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-edge border-t-brand-bright" />
        <p className="text-sm font-medium text-ink">Analyzing clinical trials…</p>
      </div>
      {query && <p className="mt-2 truncate text-sm text-muted">“{query}”</p>}

      {/* A chart-shaped placeholder, so the layout does not jump on arrival. */}
      <div className="mt-6 flex h-56 items-end gap-2 sm:h-72" aria-hidden="true">
        {[42, 68, 30, 84, 56, 74, 38, 62, 48, 90, 34, 58].map((height, index) => (
          <div
            key={index}
            className="flex-1 rounded-t bg-brand"
            style={{
              height: `${height}%`,
              animation: `pulse-bar 1.4s ease-in-out ${index * 0.08}s infinite`,
            }}
          />
        ))}
      </div>
      <ul className="mt-5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        <li>Planning the query</li>
        <li>Retrieving ClinicalTrials.gov studies</li>
        <li>Aggregating and tracing sources</li>
      </ul>
    </section>
  );
}

/**
 * Every failure, in one shape: icon, human heading, human message, and a
 * discreet request id. Raw JSON is never the primary content — the structured
 * details stay collapsed behind a disclosure for the rare case they help.
 */
export function ErrorState({ error }: { error: ApiError }) {
  const copy = FRIENDLY[error.code] ?? FALLBACK;
  const noResults = error.code === "NO_MATCHING_TRIALS";
  const details = Object.entries(error.details ?? {});

  return (
    <section
      role="alert"
      className="rounded-card border bg-card p-8 text-center shadow-card"
      style={{ borderColor: noResults ? "var(--color-edge)" : "rgba(255, 68, 68, 0.3)" }}
    >
      <div className="mx-auto flex flex-col items-center gap-4">
        <span
          className={`flex h-12 w-12 items-center justify-center rounded-full ${
            noResults ? "bg-brand/15 text-brand-bright" : "bg-danger/10 text-danger"
          }`}
        >
          {noResults ? (
            <SearchIcon className="h-6 w-6" />
          ) : (
            <AlertIcon className="h-6 w-6" />
          )}
        </span>

        <div>
          <h2 className="text-lg font-semibold text-ink">{copy.heading}</h2>
          <p className="mx-auto mt-1.5 max-w-md text-sm text-muted">{copy.message}</p>
        </div>

        {!noResults && error.message && (
          <p className="mx-auto max-w-md text-xs text-muted/80">{error.message}</p>
        )}

        {details.length > 0 && (
          <details className="w-full max-w-md text-left">
            <summary className="cursor-pointer text-xs font-medium text-muted hover:text-ink">
              Technical details
            </summary>
            <pre className="mt-2 max-h-48 overflow-auto rounded-control border border-edge bg-canvas p-3 text-left text-xs leading-5 text-muted">
              {JSON.stringify(error.details, null, 2)}
            </pre>
          </details>
        )}

        {error.request_id && (
          <p className="font-mono text-[11px] text-muted/60">Request ID: {error.request_id}</p>
        )}
      </div>
    </section>
  );
}

export function EmptyState({
  examples,
  onPick,
}: {
  examples: ExampleQuery[];
  onPick: (query: string) => void;
}) {
  return (
    <section className="rounded-card border border-edge bg-card p-8 text-center shadow-card sm:p-12">
      <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-brand/15 text-brand-bright">
        <ChartIcon className="h-6 w-6" />
      </span>
      <h2 className="mt-4 text-xl font-semibold text-ink">Ask a question about clinical trials</h2>
      <p className="mx-auto mt-2 max-w-lg text-sm text-muted">
        Every answer is a chart built from live ClinicalTrials.gov records — trends over time,
        phase distributions, geography, drug↔sponsor networks — and every value links back to the
        studies that produced it.
      </p>

      {examples.length > 0 && (
        <div className="mt-7">
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Try one</p>
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {examples.slice(0, 6).map((example) => (
              <button
                key={example.label}
                type="button"
                onClick={() => onPick(example.query)}
                className="max-w-full rounded-control border border-edge bg-elevated px-3.5 py-2 text-left text-xs text-muted transition hover:border-brand hover:text-ink"
              >
                <span className="font-medium text-brand-soft">{example.label}</span>
                <span className="mx-1.5 text-edge">·</span>
                <span className="break-words">{example.query}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
