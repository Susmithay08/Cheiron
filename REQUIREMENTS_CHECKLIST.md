# Assessment Requirements Checklist

Self-audit against `ASSESSMENT.md`. Items are checked only where the behaviour
actually works and is covered by a test or a generated example.

## Required (§3 Functional Requirements)

- [x] **Natural-language query input** — `query`, required, 3–500 chars, validated (`api/schemas.py`)
- [x] **Optional structured input fields** — `drug_name`, `condition`, `trial_phase`, `sponsor`, `country`, `start_year`, `end_year`, `status`
- [x] **Request schema documented** — field/type/required/validation table in README + OpenAPI at `/docs`
- [x] **Uses the ClinicalTrials.gov API as the authoritative source** — `/studies` with `query.*`, `filter.overallStatus`, `filter.advanced`, `fields`, `pageSize`, `pageToken`
- [x] **Structured visualization output** — `visualization` envelope with all four required parts
  - [x] `type` — six values
  - [x] `title` — human-readable, derived from the plan
  - [x] `encoding` — x/y/series/color for cartesian charts; node/edge channels for networks
  - [x] `data` — the rendering rows (plus `nodes`/`edges` for networks)
- [x] **Response metadata** — units, sort, time granularity, grouping, filters applied, studies retrieved/matched, truncation flag, assumptions, interpretation notes
- [x] **Response schema documented** — annotated example + renderer contract in README, plus OpenAPI models
- [x] **README** — how to run, request/response schemas, design decisions, tradeoffs, limitations, improvements
- [x] **Example runs (3–5 required)** — 7 provided in `examples/`, all actual service output
- [x] **Tests** — 87 unit tests (fully mocked) + 2 opt-in live tests

## Query coverage (§4, Appendix)

- [x] **Time trends** — `time_trend` → `time_series` (`examples/01_time_trend.json`)
- [x] **Distributions** — `distribution` → `bar_chart` / `histogram` (`examples/02_distribution.json`)
- [x] **Comparisons** — `comparison` → `grouped_bar_chart` (`examples/03_comparison.json`)
- [x] **Geographic** — `geographic` → `bar_chart` by country (`examples/04_geographic.json`)
- [x] **Networks** — `relationship` → `network_graph`, four relationship kinds (`examples/05_network.json`)
- [x] **Scatter / correlation** — `correlation` → `scatter_plot` (`examples/06_correlation.json`)
- [x] **Single coherent approach, not per-query hacks** — one plan model, one executor, one router; adding an intent means adding an enum value + extractor + builder

## Visualization types (§4)

- [x] `bar_chart`
- [x] `grouped_bar_chart`
- [x] `time_series`
- [x] `scatter_plot`
- [x] `histogram`
- [x] `network_graph` — pruned by connectivity, placebo-class nodes excluded, edges weighted by co-occurring studies

## AI / agent design (§7.2)

- [x] **Structured planner** — LLM emits a `QueryPlan`, never an answer
- [x] **Constrained output** — every field is an enum; `extra="forbid"` rejects invented keys
- [x] **Planner validation + bounded repair** — one repair round, then deterministic fallback
- [x] **Tool separation** — planning, retrieval, aggregation, building, tracing and validation are separate modules
- [x] **Deterministic aggregation** — every count/sum/median/bin/edge weight computed in Python
- [x] **Visualization selection validated** — backend router overrides invalid LLM suggestions and records the override
- [x] **Output validation** — encoding/data agreement, numeric finiteness, network integrity, citation integrity
- [x] **Error handling** — nine structured error codes; no stack traces leak to clients
- [x] **Ambiguous queries handled** — answered with the interpretation and assumptions disclosed, not refused

## Bonus (§5 Deep citations)

- [x] **Each visualized datum references underlying trial records** — bars, time buckets, histogram bins, scatter points and network edges all carry `citations`
- [x] **Each reference includes `nct_id`**
- [x] **Each reference includes an exact field/value from the API response** — `field` gives the CT.gov path, `value` the exact value read, `excerpt` the study title
- [x] **Sensible strategy for large result sets** — capped detail (5/datum, deterministic) plus complete provenance (`supporting_trial_count`, `supporting_nct_ids`); documented in README
- [x] **Citations cannot be fabricated** — tracer builds only from retrieved trials; the validator independently re-checks every ID and rejects the response otherwise

## Bonus (§6.4 Optional demo)

- [x] **Frontend demo** — React + TypeScript + Vite + Tailwind + Recharts
- [x] **Generic renderer** — one switch on `visualization.type`, no per-query code
- [x] **All six chart types rendered**
- [x] **Network graph** — force-directed, pan, zoom, hover highlight, edge weights, legend
- [x] **Loading / error / empty states**
- [x] **Example query buttons + query history**
- [x] **Citation panel** — click any datum for NCT IDs, field paths, exact values, clickable links
- [x] **Responsive layout**
- [ ] **Deployed public endpoint** — not deployed; runs locally. Out of scope for the time box.
- [ ] **Demo video** — not recorded.

## Engineering quality

- [x] **Async I/O** — httpx throughout; comparison series fetched concurrently
- [x] **Pagination** — full `nextPageToken` traversal with a disclosed cap
- [x] **Retries with backoff** — 5xx/429 retried, 400 not retried
- [x] **TTL cache** — in-process, 15 min, documented tradeoff vs Redis
- [x] **Field selection from the plan** — only the fields the aggregation reads
- [x] **Missing-data safety** — flat normalization; no crash on any absent nested field
- [x] **Structured logging** — JSON events correlated by request ID, credentials scrubbed
- [x] **Secrets via environment** — `.env.example` provided, `.env` gitignored, no key in source/logs/responses
- [x] **CORS configured**
- [x] **No arbitrary code execution from the LLM**
- [x] **OpenAPI docs with descriptions and examples**

## Known gaps

- [ ] **Geographic map/choropleth** — country data supports it; only a bar chart is implemented.
- [ ] **Synonym/brand-name normalization** — "Keytruda" and "Pembrolizumab" remain distinct searches.
- [ ] **Field-scoped CT.gov search** — a single `query.term` is used rather than routing entities to `query.cond` / `query.intr` / `query.spons`, so keyword matches can be loose.
- [ ] **`/stats/field/values` fast path** — implemented in the client but not yet used to bypass study fetching for simple distributions.
- [ ] **Multi-step / chained plans** — e.g. "phase distribution of the top 3 sponsors" needs one query to feed another.
- [ ] **Automated browser tests** — the frontend was verified by `tsc`, production build and per-module compilation; no browser driver was available in the build environment.
- [ ] **Auth / rate limiting** — the service assumes a trusted local deployment.
