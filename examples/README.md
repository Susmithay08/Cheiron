# Example runs

Actual JSON returned by the running service (`POST /analyze`), not handwritten.
Regenerate with `python backend/scripts/generate_examples.py` against a local
backend; the numbers move as the registry does.

| File | Query | Status | Result |
|------|-------|--------|--------|
| `01_time_trend.json` | How has the number of trials for this drug changed per year since 2015? (drug_name=Pembrolizumab, start_year=2015) | 200 | `time_series` — 13 rows, 3,026 studies |
| `02_distribution.json` | How are breast cancer trials distributed across phases? | 200 | `bar_chart` — 6 rows, 5,000 studies |
| `03_comparison.json` | Compare trial counts by phase for Ozempic vs Wegovy | 200 | `grouped_bar_chart` — 12 rows, 220 studies |
| `04_geographic.json` | Which countries have the most recruiting trials for Alzheimer's disease? | 200 | `bar_chart` — 15 rows, 832 studies |
| `05_network.json` | Show a network of sponsors and drugs for diabetes trials | 200 | `network_graph` — 29 nodes / 56 edges, 5,000 studies |
| `06_correlation.json` | Is there a relationship between enrollment and start year for uveal melanoma trials? | 200 | `scatter_plot` — 306 rows, 318 studies |
| `07_error_no_matching_trials.json` | How many trials exist for zzqqxx-nonexistent-compound? | 404 | `NO_MATCHING_TRIALS` |
| `08_histogram.json` | Show the distribution of enrollment sizes for glioblastoma trials | 200 | `histogram` — 13 rows, 2,456 studies |
| `09_intent_hint.json` | How are breast cancer trials distributed across phases? (intent_hint=time_trend) | 200 | `time_series` — 52 rows, 5,000 studies |

Every file has the shape `{request, http_status, response}`, so the request that
produced an output always sits next to it.

`09_intent_hint.json` is the same question as `02_distribution.json` with
`intent_hint: "time_trend"` added: the UI's analysis-type chips re-frame a
question without rewriting it.
