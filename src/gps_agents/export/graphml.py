"""GraphML export for family tree network visualization.

GraphML is an XML-based format for graph data, supported by:
- Gephi (network analysis)
- yEd (graph editor)
- Cytoscape (biological networks, works for genealogy)
- NetworkX (Python network library)
- Neo4j (graph database import)

This format is ideal for:
- Visualizing complex family relationships
- Network analysis (clustering, centrality)
- Identifying relationship patterns
- Exporting to graph databases
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.models.fact import FactStatus


@dataclass
class GraphNode:
    """Node in the family tree graph."""

    id: str
    label: str
    node_type: str = "person"  # person, family, event
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """Edge in the family tree graph."""

    source: str
    target: str
    edge_type: str  # parent_of, spouse_of, child_of, etc.
    label: str = ""
    attributes: dict[str, str] = field(default_factory=dict)


def _parse_person_key(person_key: str) -> tuple[str, str | None, str | None]:
    """Parse person_id key into name components."""
    parts = person_key.split("|")
    name_part = parts[0].strip() if parts else ""

    if not name_part:
        return "Unknown", None, None

    name_parts = name_part.split()
    if len(name_parts) == 1:
        return name_part, name_part, None
    else:
        given = " ".join(name_parts[:-1])
        surname = name_parts[-1]
        return name_part, given, surname


def _sanitize_id(s: str) -> str:
    """Sanitize string for use as XML ID."""
    import re
    # Replace non-alphanumeric with underscore, ensure starts with letter
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", s)
    if sanitized and not sanitized[0].isalpha():
        sanitized = "n" + sanitized
    return sanitized or "unknown"


def export_graphml(
    ledger_dir: Path,
    out_file: Path,
    include_families: bool = True,
    include_events: bool = False,
    edge_weights: bool = True,
) -> Path:
    """Export facts and relationships to GraphML format.

    Args:
        ledger_dir: Path to the fact ledger directory
        out_file: Output file path for the GraphML file
        include_families: Create intermediate family nodes (for complex visualization)
        include_events: Include event nodes (birth, death, etc.)
        edge_weights: Include confidence as edge weights

    Returns:
        Path to the created GraphML file
    """
    ledger = FactLedger(str(ledger_dir))

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    def _ensure_person_node(person_key: str) -> str:
        """Ensure person node exists and return ID."""
        node_id = _sanitize_id(person_key)
        if node_id not in nodes:
            full_name, given, surname = _parse_person_key(person_key)
            nodes[node_id] = GraphNode(
                id=node_id,
                label=full_name,
                node_type="person",
                attributes={
                    "given_name": given or "",
                    "surname": surname or "",
                    "full_key": person_key,
                },
            )
        return node_id

    family_counter = 0

    def _ensure_family_node(spouse1_id: str, spouse2_id: str | None = None) -> str:
        """Create family node for spouse grouping."""
        nonlocal family_counter

        # Create unique family key
        if spouse2_id:
            key = tuple(sorted([spouse1_id, spouse2_id]))
            fam_id = f"fam_{key[0]}_{key[1]}"
        else:
            fam_id = f"fam_{spouse1_id}_{family_counter}"
            family_counter += 1

        if fam_id not in nodes:
            nodes[fam_id] = GraphNode(
                id=fam_id,
                label="Family",
                node_type="family",
                attributes={},
            )

        return fam_id

    # Process all accepted facts
    for fact in ledger.iter_all_facts(FactStatus.ACCEPTED):
        fact_type = (fact.fact_type or "").lower()

        if fact_type == "relationship":
            subject = (fact.relation_subject or "").strip()
            obj = (fact.relation_object or "").strip()
            kind = (fact.relation_kind or "").lower()

            if subject and obj:
                subject_id = _ensure_person_node(subject)
                object_id = _ensure_person_node(obj)

                if include_families and kind in ("parent_of", "spouse_of", "child_of"):
                    # Create family node for complex relationships
                    if kind == "spouse_of":
                        fam_id = _ensure_family_node(subject_id, object_id)
                        # Both spouses connect to family
                        edges.append(GraphEdge(
                            source=subject_id,
                            target=fam_id,
                            edge_type="spouse",
                            label="spouse",
                            attributes={"weight": str(fact.confidence or 1.0)} if edge_weights else {},
                        ))
                        edges.append(GraphEdge(
                            source=object_id,
                            target=fam_id,
                            edge_type="spouse",
                            label="spouse",
                            attributes={"weight": str(fact.confidence or 1.0)} if edge_weights else {},
                        ))
                    elif kind == "parent_of":
                        # Direct parent -> child edge
                        edges.append(GraphEdge(
                            source=subject_id,
                            target=object_id,
                            edge_type="parent_of",
                            label="parent",
                            attributes={"weight": str(fact.confidence or 1.0)} if edge_weights else {},
                        ))
                    elif kind == "child_of":
                        # Child -> parent is reversed
                        edges.append(GraphEdge(
                            source=object_id,
                            target=subject_id,
                            edge_type="parent_of",
                            label="parent",
                            attributes={"weight": str(fact.confidence or 1.0)} if edge_weights else {},
                        ))
                else:
                    # Simple direct edge
                    edges.append(GraphEdge(
                        source=subject_id,
                        target=object_id,
                        edge_type=kind,
                        label=kind.replace("_", " "),
                        attributes={"weight": str(fact.confidence or 1.0)} if edge_weights else {},
                    ))

        elif fact.person_id:
            person_id = _ensure_person_node(fact.person_id)

            # Add fact data to node attributes
            if fact_type in ("birth", "death", "burial", "occupation"):
                nodes[person_id].attributes[fact_type] = fact.statement

            if include_events and fact_type in ("birth", "death", "burial", "marriage"):
                # Create event node
                event_id = f"event_{person_id}_{fact_type}"
                if event_id not in nodes:
                    nodes[event_id] = GraphNode(
                        id=event_id,
                        label=f"{fact_type.title()}: {fact.statement[:30]}...",
                        node_type="event",
                        attributes={
                            "event_type": fact_type,
                            "statement": fact.statement,
                        },
                    )
                    # Connect person to event
                    edges.append(GraphEdge(
                        source=person_id,
                        target=event_id,
                        edge_type="has_event",
                        label=fact_type,
                    ))

    # Build GraphML XML
    graphml = _build_graphml(nodes, edges, edge_weights)

    out_file.parent.mkdir(parents=True, exist_ok=True)

    tree = ET.ElementTree(graphml)
    ET.indent(tree, space="  ")
    tree.write(out_file, encoding="utf-8", xml_declaration=True)

    return out_file


def _build_graphml(
    nodes: dict[str, GraphNode],
    edges: list[GraphEdge],
    include_weights: bool,
) -> ET.Element:
    """Build GraphML XML structure."""
    # Namespace
    ns = "http://graphml.graphdrawing.org/xmlns"
    nsmap = {
        "xmlns": ns,
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": f"{ns} http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd",
    }

    root = ET.Element("graphml", nsmap)

    # Add metadata comment
    comment = ET.Comment(f"Generated by gps-genealogy-agents on {datetime.now(UTC).isoformat()}")
    root.append(comment)

    # Define keys (attribute definitions)
    # Node attributes
    ET.SubElement(root, "key", {
        "id": "label",
        "for": "node",
        "attr.name": "label",
        "attr.type": "string",
    })
    ET.SubElement(root, "key", {
        "id": "node_type",
        "for": "node",
        "attr.name": "node_type",
        "attr.type": "string",
    })
    ET.SubElement(root, "key", {
        "id": "given_name",
        "for": "node",
        "attr.name": "given_name",
        "attr.type": "string",
    })
    ET.SubElement(root, "key", {
        "id": "surname",
        "for": "node",
        "attr.name": "surname",
        "attr.type": "string",
    })
    ET.SubElement(root, "key", {
        "id": "birth",
        "for": "node",
        "attr.name": "birth",
        "attr.type": "string",
    })
    ET.SubElement(root, "key", {
        "id": "death",
        "for": "node",
        "attr.name": "death",
        "attr.type": "string",
    })

    # Edge attributes
    ET.SubElement(root, "key", {
        "id": "edge_type",
        "for": "edge",
        "attr.name": "edge_type",
        "attr.type": "string",
    })
    ET.SubElement(root, "key", {
        "id": "edge_label",
        "for": "edge",
        "attr.name": "label",
        "attr.type": "string",
    })
    if include_weights:
        ET.SubElement(root, "key", {
            "id": "weight",
            "for": "edge",
            "attr.name": "weight",
            "attr.type": "double",
        })

    # Create graph element
    graph = ET.SubElement(root, "graph", {
        "id": "family_tree",
        "edgedefault": "directed",
    })

    # Add nodes
    for node in nodes.values():
        node_el = ET.SubElement(graph, "node", {"id": node.id})

        # Label
        data_label = ET.SubElement(node_el, "data", {"key": "label"})
        data_label.text = node.label

        # Node type
        data_type = ET.SubElement(node_el, "data", {"key": "node_type"})
        data_type.text = node.node_type

        # Other attributes
        for attr_key, attr_val in node.attributes.items():
            if attr_val:
                data_attr = ET.SubElement(node_el, "data", {"key": attr_key})
                data_attr.text = str(attr_val)

    # Add edges
    for i, edge in enumerate(edges):
        edge_el = ET.SubElement(graph, "edge", {
            "id": f"e{i}",
            "source": edge.source,
            "target": edge.target,
        })

        # Edge type
        data_type = ET.SubElement(edge_el, "data", {"key": "edge_type"})
        data_type.text = edge.edge_type

        # Label
        data_label = ET.SubElement(edge_el, "data", {"key": "edge_label"})
        data_label.text = edge.label

        # Weight
        if include_weights and "weight" in edge.attributes:
            data_weight = ET.SubElement(edge_el, "data", {"key": "weight"})
            data_weight.text = edge.attributes["weight"]

    return root


def export_graphml_simple(
    persons: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    out_file: Path,
) -> Path:
    """Export pre-structured data to GraphML.

    Args:
        persons: List of person dictionaries with 'id', 'name', and optional attributes
        relationships: List of relationship dictionaries with 'type', 'subject_id', 'object_id'
        out_file: Output file path

    Returns:
        Path to the created GraphML file
    """
    nodes = {}
    edges = []

    for person in persons:
        node_id = _sanitize_id(person.get("id", "unknown"))
        nodes[node_id] = GraphNode(
            id=node_id,
            label=person.get("name", "Unknown"),
            node_type="person",
            attributes={
                k: str(v) for k, v in person.items()
                if k not in ("id", "name") and v
            },
        )

    for rel in relationships:
        edges.append(GraphEdge(
            source=_sanitize_id(rel.get("subject_id", "")),
            target=_sanitize_id(rel.get("object_id", "")),
            edge_type=rel.get("type", "related_to"),
            label=rel.get("type", ""),
            attributes={"weight": str(rel.get("confidence", 1.0))},
        ))

    graphml = _build_graphml(nodes, edges, include_weights=True)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(graphml)
    ET.indent(tree, space="  ")
    tree.write(out_file, encoding="utf-8", xml_declaration=True)

    return out_file
