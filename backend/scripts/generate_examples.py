"""Regenerate `examples/` from a running service.

The example outputs in this repository are real responses, not handwritten JSON.
This script is how they are produced, so any reviewer can reproduce them:

    cd backend && uvicorn app.main:app --port 8000     # terminal 1
    python backend/scripts/generate_examples.py        # terminal 2

Numbers move as ClinicalTrials.gov moves; that is expected.
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.error
import urllib.request

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = pathlib.Path(__file__).resolve().parents[2] / "examples"

CASES: list[tuple[str, dict]] = [
    ("01_time_trend", {
        "query": "How has the number of trials for this drug changed per year since 2015?",
        "drug_name": "Pembrolizumab",
        "start_year": 2015,
    }),
    ("02_distribution", {"query": "How are breast cancer trials distributed across phases?"}),
    ("03_comparison", {"query": "Compare trial counts by phase for Ozempic vs Wegovy"}),
    ("04_geographic", {
        "query": "Which countries have the most recruiting trials for Alzheimer's disease?"
    }),
    ("05_network", {"query": "Show a network of sponsors and drugs for diabetes trials"}),
    ("06_correlation", {
        "query": "Is there a relationship between enrollment and start year for uveal melanoma trials?"
    }),
    ("07_error_no_matching_trials", {
        "query": "How many trials exist for zzqqxx-nonexistent-compound?"
    }),
    ("08_histogram", {
        "query": "Show the distribution of enrollment sizes for glioblastoma trials"
    }),
    ("09_intent_hint", {
        "query": "How are breast cancer trials distributed across phases?",
        "intent_hint": "time_trend",
    }),
]


def post(payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{API}/analyze",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def summarize(body: dict) -> str:
    if "visualization" not in body:
        return f"`{body['error']['code']}`"
    viz = body["visualization"]
    shape = (
        f"{len(viz['nodes'])} nodes / {len(viz['edges'])} edges"
        if viz["type"] == "network_graph"
        else f"{len(viz['data'])} rows"
    )
    return f"`{viz['type']}` — {shape}, {viz['metadata']['studies_matched']:,} studies"


def describe(payload: dict) -> str:
    extra = ", ".join(f"{k}={v}" for k, v in payload.items() if k != "query")
    return payload["query"] + (f" ({extra})" if extra else "")


def main() -> None:
    rows = []
    for name, payload in CASES:
        status, body = post(payload)
        path = OUT / f"{name}.json"
        path.write_text(
            json.dumps({"request": payload, "http_status": status, "response": body}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        rows.append((name, payload, status, summarize(body)))
        print(f"{name:32} {status} {summarize(body)} ({path.stat().st_size / 1024:.0f} KB)")

    lines = [
        "# Example runs",
        "",
        "Actual JSON returned by the running service (`POST /analyze`), not handwritten.",
        "Regenerate with `python backend/scripts/generate_examples.py` against a local",
        "backend; the numbers move as the registry does.",
        "",
        "| File | Query | Status | Result |",
        "|------|-------|--------|--------|",
        *(
            f"| `{name}.json` | {describe(payload)} | {status} | {result} |"
            for name, payload, status, result in rows
        ),
        "",
        "Every file has the shape `{request, http_status, response}`, so the request that",
        "produced an output always sits next to it.",
        "",
        "`09_intent_hint.json` is the same question as `02_distribution.json` with",
        "`intent_hint: \"time_trend\"` added: the UI's analysis-type chips re-frame a",
        "question without rewriting it.",
        "",
    ]
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
