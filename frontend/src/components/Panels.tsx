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
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</h2>
        {right}
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

function Pill({ children, tone = "slate" }: { children: React.ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700",
    blue: "bg-blue-50 text-blue-700",
    amber: "bg-amber-50 text-amber-700",
  };
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tones[tone]}`}>{children}</span>
  );
}

export function InterpretationPanel({ response }: { response: AnalyzeResponse }) {
  const { plan, elapsed_ms } = response.meta;
  const meta = response.visualization.metadata;

  return (
    <Card
      title="Interpretation"
      right={<span className="text-xs text-slate-400">{elapsed_ms} ms</span>}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="blue">{plan.intent.replace(/_/g, " ")}</Pill>
        {plan.search_terms.map((term) => (
          <Pill key={term}>{term}</Pill>
        ))}
        {plan.dimension && <Pill>by {plan.dimension.replace(/_/g, " ")}</Pill>}
        {plan.relationship && <Pill>{plan.relationship.replace(/_/g, " ↔ ")}</Pill>}
        {Object.entries(plan.filters).map(([key, value]) => (
          <Pill key={key} tone="amber">
            {key}: {Array.isArray(value) ? value.join(", ") : String(value)}
          </Pill>
        ))}
        <Pill>planner: {plan.planner_mode}</Pill>
      </div>
      {plan.interpretation && <p className="mt-3 text-sm text-slate-600">{plan.interpretation}</p>}
      {meta.assumptions.length > 0 && (
        <ul className="mt-3 list-inside list-disc text-sm text-slate-500">
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
    ["Metric", `${meta.metric} (${meta.unit})`],
    ["Grouping", meta.grouping ?? "—"],
    ["Sort", meta.sort ? `${meta.sort.field} ${meta.sort.direction}` : "—"],
    ["Source", meta.source],
  ];

  return (
    <Card title="Filters & methodology">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3 border-b border-slate-50 py-1">
            <dt className="text-slate-500">{label}</dt>
            <dd className="text-right font-medium text-slate-800">{value}</dd>
          </div>
        ))}
      </dl>
      {meta.notes.length > 0 && (
        <ul className="mt-4 space-y-1.5 text-xs text-slate-500">
          {meta.notes.map((note) => (
            <li key={note} className="rounded-md bg-slate-50 px-3 py-2">
              {note}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function citationsOf(datum: Datum | null): Citation[] {
  return datum?.citations ?? [];
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

  return (
    <Card
      title="Source traceability"
      right={
        datum ? (
          <span className="text-xs text-slate-400">
            {datum.supporting_trial_count?.toLocaleString()} supporting studies
          </span>
        ) : null
      }
    >
      {!datum ? (
        <p className="text-sm text-slate-500">
          Click any bar, point or edge to see the ClinicalTrials.gov records behind it.
          This response covers {fallbackCount.toLocaleString()} data points.
        </p>
      ) : (
        <>
          <p className="mb-3 text-sm text-slate-600">
            Showing {citations.length} of {datum.supporting_trial_count?.toLocaleString()} studies
            that produced <span className="font-semibold text-slate-900">{label}</span>.
          </p>
          <ul className="space-y-2">
            {citations.map((citation) => (
              <li key={`${citation.nct_id}-${citation.field}`} className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
                <div className="flex items-baseline justify-between gap-3">
                  <a
                    href={citation.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono text-sm font-semibold text-blue-700 hover:underline"
                  >
                    {citation.nct_id}
                  </a>
                  <code className="truncate text-xs text-slate-400">{citation.field}</code>
                </div>
                <p className="mt-1 text-sm text-slate-700">{citation.excerpt}</p>
                <p className="mt-1 text-xs text-slate-500">
                  Supporting value: <span className="font-medium text-slate-700">{citation.value}</span>
                </p>
              </li>
            ))}
          </ul>
          {(datum.supporting_nct_ids?.length ?? 0) > citations.length && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-medium text-slate-500 hover:text-slate-700">
                All contributing NCT IDs ({datum.supporting_nct_ids!.length})
              </summary>
              <p className="mt-2 break-words font-mono text-xs leading-5 text-slate-500">
                {datum.supporting_nct_ids!.join(", ")}
              </p>
            </details>
          )}
        </>
      )}
    </Card>
  );
}
