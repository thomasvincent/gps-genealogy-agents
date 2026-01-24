"""Export modules for family tree data.

Supported formats:
- GEDCOM 5.5: Standard genealogy interchange format
- JSON: Structured data for APIs and analysis
- Markdown: Human-readable documentation
- GraphML: Network visualization (Gephi, yEd, Cytoscape)
- PDF: Printable documents (requires weasyprint)
- Mermaid: Diagram markup for GitHub/GitLab
"""
from __future__ import annotations

from gps_agents.export.gedcom import export_gedcom, GedcomIndividual, GedcomFamily, GedcomEvent
from gps_agents.export.json_export import (
    export_json,
    export_json_simple,
    PersonExport,
    RelationshipExport,
    FamilyTreeExport,
)
from gps_agents.export.markdown import (
    export_markdown,
    export_markdown_report,
    MarkdownPerson,
)
from gps_agents.export.graphml import (
    export_graphml,
    export_graphml_simple,
    GraphNode,
    GraphEdge,
)
from gps_agents.export.pdf import (
    export_pdf,
    export_pdf_simple,
    PDFPerson,
)
from gps_agents.export.mermaid import export_mermaid

__all__ = [
    # GEDCOM export
    "export_gedcom",
    "GedcomIndividual",
    "GedcomFamily",
    "GedcomEvent",
    # JSON export
    "export_json",
    "export_json_simple",
    "PersonExport",
    "RelationshipExport",
    "FamilyTreeExport",
    # Markdown export
    "export_markdown",
    "export_markdown_report",
    "MarkdownPerson",
    # GraphML export
    "export_graphml",
    "export_graphml_simple",
    "GraphNode",
    "GraphEdge",
    # PDF export
    "export_pdf",
    "export_pdf_simple",
    "PDFPerson",
    # Mermaid export
    "export_mermaid",
]


# Format detection utility
EXPORT_FORMATS = {
    ".ged": export_gedcom,
    ".gedcom": export_gedcom,
    ".json": export_json,
    ".md": export_markdown,
    ".markdown": export_markdown,
    ".graphml": export_graphml,
    ".pdf": export_pdf,
    ".html": export_pdf,  # PDF falls back to HTML
}


def export_by_format(ledger_dir, out_file, **kwargs):
    """Export to format based on file extension.

    Args:
        ledger_dir: Path to fact ledger
        out_file: Output file path (extension determines format)
        **kwargs: Format-specific options

    Returns:
        Path to created file

    Raises:
        ValueError: If format not supported
    """
    from pathlib import Path

    out_path = Path(out_file)
    suffix = out_path.suffix.lower()

    if suffix not in EXPORT_FORMATS:
        supported = ", ".join(EXPORT_FORMATS.keys())
        raise ValueError(f"Unsupported format '{suffix}'. Supported: {supported}")

    export_func = EXPORT_FORMATS[suffix]
    return export_func(Path(ledger_dir), out_path, **kwargs)
