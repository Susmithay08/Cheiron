/** Interpretation, methodology and source-traceability panels. */

import type { AnalyzeResponse, Citation, Datum, Visualization } from "../types/api";

export function Card({
  title,
  children,
  right,
}: {
  title: string;
  children: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <section className="rounded-card border border-edge bg-card shadow-card">
      <header className="flex items-center justify-between gap-3 border-b border-edge px-5 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</h2>
        {right}
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

function Pill({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "brand" | "filter";
}) {
  const tones = {
    neutral: "border-edge bg-elevated text-muted",
    brand: "border-brand bg-brand/15 text-brand-soft",
    filter: "border-brand-deep bg-brand-deep/25 text-brand-soft",
  } as const;
  return (
    <span className={`rounded-control border px-2.5 py-1 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

/** The plan's intent, in the UI's own words rather than backend vocabulary. */
export const INTENT_LABELS: Record<string, string> = {
  time_trend: "Time trend",
  distribution: "Distribution",
  comparison: "Comparison",
  geographic: "Geography",
  relationship: "Network",
  correlation: "Correlation",
};

export function IntentBadge({ intent }: { intent: string }) {
  return (
    <span className="rounded-control border border-brand bg-brand/15 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-brand-soft">
      {INTENT_LABELS[intent] ?? intent.replace(/_/g, " ")}
    </span>
  );
}

export function InterpretationPanel({ response }: { response: AnalyzeResponse }) {
  const { plan, elapsed_ms } = response.meta;
  const meta = response.visualization.metadata;

  return (
    <Card
      title="Interpretation"
      right={
        <div className="flex items-center gap-2">
          <IntentBadge intent={plan.intent} />
          <span className="text-xs text-muted">{elapsed_ms.toLocaleString()} ms</span>
        </div>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        {plan.search_terms.map((term) => (
          <Pill key={term}>{term}</Pill>
        ))}
        {plan.dimension && <Pill>by {plan.dimension.replace(/_/g, " ")}</Pill>}
        {plan.relationship && <Pill>{plan.relationship.replace(/_/g, " ↔ ")}</Pill>}
        {Object.entries(plan.filters).map(([key, value]) => (
          <Pill key={key} tone="filter">
            {key}: {Array.isArray(value) ? value.join(", ") : String(value)}
          </Pill>
        ))}
        <Pill>planner: {plan.planner_mode}</Pill>
      </div>
      {plan.interpretation && <p className="mt-3 text-sm text-ink/80">{plan.interpretation}</p>}
      {meta.assumptions.length > 0 && (
        <ul className="mt-3 list-inside list-disc text-sm text-muted">
          {meta.assumptions.map((assumption) => (
            <li key={assumption}>{assumption}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function MethodologyPanel({ visualization }: { visualization: Visualization }) {
  const meta = visualization.metadata;
  const rows: [string, string][] = [
    ["Studies retrieved", meta.studies_retrieved.toLocaleString()],
    ["Studies after filters", meta.studies_matched.toLocaleString()],
    ...(meta.studies_available
      ? ([["Matching on the registry", meta.studies_available.toLocaleString()]] as [
          string,
          string,
        ][])
      : []),
    ["Metric", `${meta.metric} (${meta.unit})`],
    ["Grouping", meta.grouping ?? "—"],
    ["Sort", meta.sort ? `${meta.sort.field} ${meta.sort.direction}` : "—"],
    ["Complete result set", meta.truncated ? "No — capped sample" : "Yes"],
    ["Source", meta.source],
  ];

  return (
    <Card title="Filters & methodology">
      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3 border-b border-edge/60 py-1.5">
            <dt className="text-muted">{label}</dt>
            <dd className="text-right font-medium text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      {meta.notes.length > 0 && (
        <ul className="mt-4 space-y-1.5 text-xs text-muted">
          {meta.notes.map((note) => (
            <li key={note} className="rounded-control border border-edge bg-elevated px-3 py-2">
              {note}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function citationsOf(datum: Datum | null): Citation[] {
  return Array.isArray(datum?.citations) ? datum!.citations! : [];
}

export function CitationPanel({
  datum,
  label,
  fallbackCount,
}: {
  datum: Datum | null;
  label: string;
  fallbackCount: number;
}) {
  const citations = citationsOf(datum);
  const supporting = datum?.supporting_trial_count ?? 0;

  return (
    <Card
      title="Source traceability"
      right={
        datum ? (
          <span className="text-xs text-muted">
            {supporting.toLocaleString()} supporting studies
          </span>
        ) : null
      }
    >
      {!datum ? (
        <p className="text-sm text-muted">
          Click any bar, point or edge to see the ClinicalTrials.gov records behind it. This
          response covers {fallbackCount.toLocaleString()} data points.
        </p>
      ) : (
        <>
          <p className="mb-3 text-sm text-muted">
            Showing {citations.length} of {supporting.toLocaleString()} studies that produced{" "}
            <span className="font-semibold text-ink">{label}</span>.
          </p>
          <ul className="space-y-2">
            {citations.map((citation) => (
              <li
                key={`${citation.nct_id}-${citation.field}`}
                className="rounded-control border border-edge bg-elevated p-3"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <a
                    href={citation.url}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-control border border-brand bg-brand/15 px-2 py-0.5 font-mono text-xs font-semibold text-brand-soft transition hover:border-brand-bright hover:bg-brand/25 hover:text-ink"
                  >
                    {citation.nct_id}
                  </a>
                  <code className="max-w-full truncate text-[11px] text-muted" title={citation.field}>
                    {citation.field}
                  </code>
                </div>
                <p className="mt-2 text-sm text-ink/80">{citation.excerpt}</p>
                <p className="mt-1.5 text-xs text-muted">
                  Supporting value:{" "}
                  <span className="font-medium text-brand-soft">{citation.value}</span>
                </p>
              </li>
            ))}
          </ul>
          {(datum.supporting_nct_ids?.length ?? 0) > citations.length && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-medium text-muted hover:text-ink">
                {/* The backend caps this list, so never call it "all" when it is capped. */}
                Contributing NCT IDs (
                {datum.supporting_nct_ids!.length < supporting
                  ? `first ${datum.supporting_nct_ids!.length} of ${supporting.toLocaleString()}`
                  : datum.supporting_nct_ids!.length}
                )
              </summary>
              <p className="mt-2 max-h-40 overflow-auto break-words rounded-control border border-edge bg-canvas p-3 font-mono text-xs leading-5 text-muted">
                {datum.supporting_nct_ids!.join(", ")}
              </p>
            </details>
          )}
        </>
      )}
    </Card>
  );
}
