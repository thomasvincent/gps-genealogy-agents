from __future__ import annotations

from pathlib import Path
from typing import Set, Tuple

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.models.fact import FactStatus


def export_mermaid(ledger_dir: Path, out_file: Path, root_filter: str = "") -> Path:
    """Export a mermaid graph (flowchart TD) of parent/spouse/child relationships."""
    ledger = FactLedger(str(ledger_dir))

    edges: Set[Tuple[str, str, str]] = set()  # (kind, A, B)
    names: Set[str] = set()

    for fact in ledger.iter_all_facts(FactStatus.ACCEPTED):
        if fact.fact_type != "relationship":
            continue
        kind = (fact.relation_kind or "").lower()
        a = (fact.relation_subject or "").strip()
        b = (fact.relation_object or "").strip()
        if not a or not b:
            continue
        if root_filter and (root_filter.lower() not in a.lower() and root_filter.lower() not in b.lower()):
            continue
        edges.add((kind, a, b))
        names.update([a, b])

    lines = ["flowchart TD"]
    # Define nodes
    for n in sorted(names):
        nid = _node_id(n)
        lines.append(f"  {nid}[\"{n}\"]")

    # Define edges
    for kind, a, b in sorted(edges):
        na = _node_id(a)
        nb = _node_id(b)
        if kind == "child_of":
            # a is child of b (parent -> child direction: b --> a)
            lines.append(f"  { _node_id(b) } --> { _node_id(a) }")
        elif kind == "parent_of":
            lines.append(f"  { _node_id(a) } --> { _node_id(b) }")
        elif kind == "spouse_of":
            lines.append(f"  {na} --- {nb}")
        else:
            lines.append(f"  {na} -. {kind}.-> {nb}")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines), encoding="utf-8")
    return out_file


def _node_id(name: str) -> str:
    # Generate a mermaid-safe identifier
    return "N_" + "_".join(ch if ch.isalnum() else "_" for ch in name)[:60]
