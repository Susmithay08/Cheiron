"""Final gate before a visualization leaves the service.

Catches the failure modes that would break a renderer or, worse, show a number
that no retrieved trial supports:

* encoding channels pointing at fields that are absent from `data`
* non-numeric or NaN/inf values on a quantitative channel
* citations referencing NCT IDs that were never retrieved
* structurally broken networks (edges pointing at missing nodes)
"""

from __future__ import annotations

import math
from typing import Iterable

from app.visualization.schemas import Visualization


class OutputValidationError(RuntimeError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems
        self.code = "INVALID_VISUALIZATION"


def validate_visualization(viz: Visualization, known_nct_ids: Iterable[str]) -> None:
    """Raise OutputValidationError if the spec is not safely renderable."""
    known = set(known_nct_ids)
    problems: list[str] = []

    if viz.type == "network_graph":
        problems += _validate_network(viz)
    else:
        problems += _validate_cartesian(viz)

    problems += _validate_citations(viz, known)

    if problems:
        raise OutputValidationError(problems)


def _quantitative_ok(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_cartesian(viz: Visualization) -> list[str]:
    problems: list[str] = []
    if not viz.data:
        return ["visualization has no data points"]

    channels = [
        ("x", viz.encoding.x),
        ("y", viz.encoding.y),
        ("series", viz.encoding.series),
        ("color", viz.encoding.color),
    ]
    sample = viz.data[0]
    for name, channel in channels:
        if channel is None:
            continue
        if channel.field not in sample:
            problems.append(f"encoding.{name} references field '{channel.field}' absent from data")
            continue
        if channel.type == "quantitative":
            bad = [r for r in viz.data if not _quantitative_ok(r.get(channel.field))]
            if bad:
                problems.append(
                    f"encoding.{name} field '{channel.field}' has {len(bad)} non-numeric "
                    "or non-finite value(s)"
                )
    if viz.encoding.x is None or viz.encoding.y is None:
        problems.append(f"{viz.type} requires both x and y encodings")
    return problems


def _validate_network(viz: Visualization) -> list[str]:
    problems: list[str] = []
    nodes, edges = viz.nodes or [], viz.edges or []
    if not nodes or not edges:
        return ["network_graph requires at least one node and one edge"]

    enc = viz.encoding
    for name in ("node_id", "edge_source", "edge_target", "edge_weight"):
        if not getattr(enc, name):
            problems.append(f"network_graph encoding is missing '{name}'")
    if problems:
        return problems

    node_ids = {n.get(enc.node_id) for n in nodes}
    for edge in edges:
        if edge.get(enc.edge_source) not in node_ids:
            problems.append(f"edge source '{edge.get(enc.edge_source)}' has no matching node")
        if edge.get(enc.edge_target) not in node_ids:
            problems.append(f"edge target '{edge.get(enc.edge_target)}' has no matching node")
        if not _quantitative_ok(edge.get(enc.edge_weight)):
            problems.append(f"edge weight '{edge.get(enc.edge_weight)}' is not numeric")
    return problems[:10]


def _validate_citations(viz: Visualization, known: set[str]) -> list[str]:
    """Every cited NCT ID must be a study this request actually retrieved."""
    problems: list[str] = []
    rows = list(viz.data) + list(viz.edges or [])
    unknown: set[str] = set()
    for row in rows:
        for citation in row.get("citations", []) or []:
            nct_id = citation.get("nct_id")
            if nct_id not in known:
                unknown.add(str(nct_id))
        for nct_id in row.get("supporting_nct_ids", []) or []:
            if nct_id not in known:
                unknown.add(str(nct_id))
    if unknown:
        problems.append(
            f"{len(unknown)} cited NCT ID(s) were not retrieved in this request "
            f"(e.g. {sorted(unknown)[:3]})"
        )
    return problems
