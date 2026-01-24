"""PDF export for family tree documentation.

Generates PDF documents suitable for:
- Printing and archival
- Sharing with family members
- GPS compliance documentation
- Family reunion handouts

Uses HTML intermediate with optional weasyprint for rendering.
Falls back to HTML if weasyprint is not available.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
import html

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.models.fact import Fact, FactStatus


@dataclass
class PDFPerson:
    """Person data for PDF export."""

    key: str
    name: str
    given_name: str | None = None
    surname: str | None = None
    birth_date: str | None = None
    birth_place: str | None = None
    death_date: str | None = None
    death_place: str | None = None
    facts: list[dict[str, Any]] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)
    spouses: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)


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


# CSS for PDF styling
PDF_CSS = """
@page {
    size: letter;
    margin: 1in;
    @bottom-center {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9pt;
        color: #666;
    }
}

body {
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #333;
}

h1 {
    font-size: 24pt;
    color: #1a1a1a;
    border-bottom: 2px solid #333;
    padding-bottom: 10px;
    margin-bottom: 20px;
}

h2 {
    font-size: 18pt;
    color: #2a2a2a;
    margin-top: 30px;
    border-bottom: 1px solid #666;
    padding-bottom: 5px;
}

h3 {
    font-size: 14pt;
    color: #3a3a3a;
    margin-top: 20px;
}

h4 {
    font-size: 12pt;
    color: #444;
    margin-top: 15px;
    margin-bottom: 5px;
}

.person-card {
    page-break-inside: avoid;
    margin-bottom: 20px;
    padding: 15px;
    border: 1px solid #ddd;
    border-radius: 5px;
    background-color: #fafafa;
}

.person-name {
    font-size: 14pt;
    font-weight: bold;
    color: #1a1a1a;
    margin-bottom: 10px;
}

.vital-dates {
    font-style: italic;
    color: #555;
    margin-bottom: 10px;
}

.fact-list {
    margin-left: 20px;
}

.fact-item {
    margin-bottom: 5px;
}

.fact-type {
    font-weight: bold;
}

.source-list {
    font-size: 9pt;
    color: #666;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid #eee;
}

.source-item {
    margin-bottom: 3px;
}

.relationship-section {
    margin-top: 10px;
}

.relationship-label {
    font-weight: bold;
    display: inline-block;
    width: 80px;
}

.summary-table {
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
}

.summary-table th,
.summary-table td {
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
}

.summary-table th {
    background-color: #f0f0f0;
}

.gps-notice {
    background-color: #e8f4e8;
    border: 1px solid #4a7c4a;
    padding: 15px;
    margin: 20px 0;
    border-radius: 5px;
}

.footer {
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #ccc;
    font-size: 9pt;
    color: #666;
    text-align: center;
}
"""


def export_pdf(
    ledger_dir: Path,
    out_file: Path,
    title: str = "Family Tree",
    include_sources: bool = True,
    include_gps_section: bool = True,
) -> Path:
    """Export facts and relationships to PDF format.

    Args:
        ledger_dir: Path to the fact ledger directory
        out_file: Output file path for the PDF file
        title: Document title
        include_sources: Include source citations
        include_gps_section: Include GPS compliance section

    Returns:
        Path to the created file (PDF if weasyprint available, else HTML)
    """
    ledger = FactLedger(str(ledger_dir))

    persons: dict[str, PDFPerson] = {}

    def _ensure_person(person_key: str) -> PDFPerson:
        """Ensure person exists and return it."""
        if person_key not in persons:
            full_name, given, surname = _parse_person_key(person_key)
            persons[person_key] = PDFPerson(
                key=person_key,
                name=full_name,
                given_name=given,
                surname=surname,
            )
        return persons[person_key]

    # Process all accepted facts
    for fact in ledger.iter_all_facts(FactStatus.ACCEPTED):
        fact_type = (fact.fact_type or "").lower()

        if fact_type == "relationship":
            subject = (fact.relation_subject or "").strip()
            obj = (fact.relation_object or "").strip()
            kind = (fact.relation_kind or "").lower()

            if subject and obj:
                subject_person = _ensure_person(subject)
                obj_person = _ensure_person(obj)

                if kind == "parent_of":
                    subject_person.children.append(obj)
                    obj_person.parents.append(subject)
                elif kind == "child_of":
                    subject_person.parents.append(obj)
                    obj_person.children.append(subject)
                elif kind == "spouse_of":
                    if obj not in subject_person.spouses:
                        subject_person.spouses.append(obj)
                    if subject not in obj_person.spouses:
                        obj_person.spouses.append(subject)

        elif fact.person_id:
            person = _ensure_person(fact.person_id)

            person.facts.append({
                "type": fact_type,
                "statement": fact.statement,
            })

            # Extract specific fields
            if fact_type == "birth":
                person.birth_date = _extract_date(fact.statement)
                person.birth_place = _extract_place(fact.statement)
            elif fact_type == "death":
                person.death_date = _extract_date(fact.statement)
                person.death_place = _extract_place(fact.statement)

            if include_sources and fact.sources:
                for src in fact.sources:
                    person.sources.append({
                        "title": src.title or "Source",
                        "url": src.url,
                    })

    # Generate HTML
    html_content = _generate_html(
        persons=persons,
        title=title,
        include_sources=include_sources,
        include_gps_section=include_gps_section,
    )

    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Try to use weasyprint for PDF
    try:
        from weasyprint import HTML, CSS

        pdf_path = out_file.with_suffix(".pdf")
        HTML(string=html_content).write_pdf(
            pdf_path,
            stylesheets=[CSS(string=PDF_CSS)],
        )
        return pdf_path

    except ImportError:
        # Fall back to HTML
        html_path = out_file.with_suffix(".html")
        html_path.write_text(html_content, encoding="utf-8")
        return html_path


def _generate_html(
    persons: dict[str, PDFPerson],
    title: str,
    include_sources: bool,
    include_gps_section: bool,
) -> str:
    """Generate HTML content for PDF."""
    lines = []

    lines.append("<!DOCTYPE html>")
    lines.append("<html lang='en'>")
    lines.append("<head>")
    lines.append(f"<title>{html.escape(title)}</title>")
    lines.append("<meta charset='utf-8'>")
    lines.append(f"<style>{PDF_CSS}</style>")
    lines.append("</head>")
    lines.append("<body>")

    # Title
    lines.append(f"<h1>{html.escape(title)}</h1>")
    lines.append(f"<p><em>Generated on {datetime.now(UTC).strftime('%B %d, %Y')}</em></p>")

    # Summary
    lines.append("<h2>Summary</h2>")
    lines.append("<table class='summary-table'>")
    lines.append("<tr><th>Metric</th><th>Count</th></tr>")
    lines.append(f"<tr><td>Total Individuals</td><td>{len(persons)}</td></tr>")

    surnames = set(p.surname for p in persons.values() if p.surname)
    lines.append(f"<tr><td>Distinct Surnames</td><td>{len(surnames)}</td></tr>")
    lines.append("</table>")

    # GPS Section
    if include_gps_section:
        lines.append("<div class='gps-notice'>")
        lines.append("<h3>GPS Compliance Statement</h3>")
        lines.append("<p>This family tree follows the <strong>Genealogical Proof Standard</strong>:</p>")
        lines.append("<ol>")
        lines.append("<li>Reasonably exhaustive search of relevant sources</li>")
        lines.append("<li>Complete and accurate citation of sources</li>")
        lines.append("<li>Analysis and correlation of collected evidence</li>")
        lines.append("<li>Resolution of conflicting evidence</li>")
        lines.append("<li>Written conclusion based on evidence</li>")
        lines.append("</ol>")
        lines.append("</div>")

    # Persons by surname
    lines.append("<h2>Individuals</h2>")

    by_surname: dict[str, list[PDFPerson]] = {}
    for person in persons.values():
        surname = person.surname or "Unknown"
        if surname not in by_surname:
            by_surname[surname] = []
        by_surname[surname].append(person)

    for surname in sorted(by_surname.keys()):
        lines.append(f"<h3>{html.escape(surname)}</h3>")

        for person in sorted(by_surname[surname], key=lambda p: p.name):
            lines.append("<div class='person-card'>")
            lines.append(f"<div class='person-name'>{html.escape(person.name)}</div>")

            # Vital dates
            vital = []
            if person.birth_date:
                birth_str = f"b. {person.birth_date}"
                if person.birth_place:
                    birth_str += f", {person.birth_place}"
                vital.append(birth_str)
            if person.death_date:
                death_str = f"d. {person.death_date}"
                if person.death_place:
                    death_str += f", {person.death_place}"
                vital.append(death_str)
            if vital:
                lines.append(f"<div class='vital-dates'>{' — '.join(vital)}</div>")

            # Relationships
            if person.parents or person.spouses or person.children:
                lines.append("<div class='relationship-section'>")
                if person.parents:
                    lines.append(f"<div><span class='relationship-label'>Parents:</span> {', '.join(person.parents)}</div>")
                if person.spouses:
                    lines.append(f"<div><span class='relationship-label'>Spouse(s):</span> {', '.join(person.spouses)}</div>")
                if person.children:
                    lines.append(f"<div><span class='relationship-label'>Children:</span> {', '.join(person.children)}</div>")
                lines.append("</div>")

            # Facts
            if person.facts:
                lines.append("<div class='fact-list'>")
                for fact in person.facts:
                    fact_type = html.escape(fact["type"].title())
                    statement = html.escape(fact["statement"])
                    lines.append(f"<div class='fact-item'><span class='fact-type'>{fact_type}:</span> {statement}</div>")
                lines.append("</div>")

            # Sources
            if include_sources and person.sources:
                lines.append("<div class='source-list'>")
                lines.append("<strong>Sources:</strong>")
                for src in person.sources:
                    title = html.escape(src["title"])
                    if src.get("url"):
                        lines.append(f"<div class='source-item'>• <a href='{src['url']}'>{title}</a></div>")
                    else:
                        lines.append(f"<div class='source-item'>• {title}</div>")
                lines.append("</div>")

            lines.append("</div>")

    # Footer
    lines.append("<div class='footer'>")
    lines.append("<p>Generated by GPS Genealogy Agents</p>")
    lines.append("</div>")

    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


def _extract_date(statement: str) -> str | None:
    """Extract date from statement."""
    import re

    patterns = [
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{4})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, statement, re.I)
        if match:
            return match.group(1)

    return None


def _extract_place(statement: str) -> str | None:
    """Extract place from statement."""
    import re

    patterns = [
        r"\b(?:in|at)\s+([A-Z][a-z]+(?:,?\s+[A-Z][a-z]+)*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, statement)
        if match:
            return match.group(1)

    return None


def export_pdf_simple(
    persons: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    out_file: Path,
    title: str = "Family Tree",
) -> Path:
    """Export pre-structured data to PDF/HTML.

    Args:
        persons: List of person dictionaries
        relationships: List of relationship dictionaries
        out_file: Output file path
        title: Document title

    Returns:
        Path to the created file
    """
    html_content = _generate_simple_html(persons, relationships, title)

    out_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        from weasyprint import HTML, CSS

        pdf_path = out_file.with_suffix(".pdf")
        HTML(string=html_content).write_pdf(
            pdf_path,
            stylesheets=[CSS(string=PDF_CSS)],
        )
        return pdf_path

    except ImportError:
        html_path = out_file.with_suffix(".html")
        html_path.write_text(html_content, encoding="utf-8")
        return html_path


def _generate_simple_html(
    persons: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    title: str,
) -> str:
    """Generate simple HTML from structured data."""
    lines = []

    lines.append("<!DOCTYPE html>")
    lines.append(f"<html><head><title>{html.escape(title)}</title>")
    lines.append(f"<style>{PDF_CSS}</style></head><body>")
    lines.append(f"<h1>{html.escape(title)}</h1>")

    for person in persons:
        name = html.escape(person.get("name", "Unknown"))
        lines.append(f"<div class='person-card'>")
        lines.append(f"<div class='person-name'>{name}</div>")

        if person.get("birth_date"):
            lines.append(f"<p>Born: {html.escape(str(person['birth_date']))}</p>")
        if person.get("death_date"):
            lines.append(f"<p>Died: {html.escape(str(person['death_date']))}</p>")

        lines.append("</div>")

    lines.append("</body></html>")
    return "\n".join(lines)
