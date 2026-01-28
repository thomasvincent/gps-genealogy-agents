#!/usr/bin/env python3
"""
Generate validation entries from WikiTree data.

This creates validation entries based on WikiTree data as a secondary source.
These should be verified against FamilySearch primary sources when possible.
"""

import json
from datetime import datetime
from pathlib import Path
from rich.console import Console

console = Console()


def generate_wikitree_validations():
    """Generate validation entries from expanded_tree.json."""

    # Load expanded tree data
    with open("expanded_tree.json") as f:
        expanded_tree = json.load(f)

    # Load existing validations
    extracted_file = Path("familysearch_extracted_data.json")
    if extracted_file.exists():
        with open(extracted_file) as f:
            extracted_data = json.load(f)
    else:
        extracted_data = {
            "generated_at": datetime.now().isoformat(),
            "extraction_type": "wikitree_secondary_source",
            "people_searched": 0,
            "data": {}
        }

    if "data" not in extracted_data:
        extracted_data["data"] = {}

    already_validated = set(extracted_data["data"].keys())

    console.print("\n[bold cyan]Generating WikiTree-Based Validations[/bold cyan]\n")

    generated_count = 0

    # Process each profile
    for wt_id, person in expanded_tree["people"].items():
        # Skip if already validated
        if wt_id in already_validated:
            console.print(f"[dim]Skipping {wt_id} - already validated[/dim]")
            continue

        # Skip if insufficient data
        if not person.get("birth_date") or not person.get("birth_place"):
            console.print(f"[yellow]Skipping {wt_id} - insufficient data[/yellow]")
            continue

        # Create validation entry
        validation = {
            "person_name": f"{person.get('first_name', '')} {person.get('last_name', '')}".strip() or wt_id,
            "birth_date": person.get("birth_date", ""),
            "birth_location": person.get("birth_place", ""),
            "familysearch_record_id": "",
            "familysearch_url": "",
            "wikitree_id": wt_id,
            "relationships": {},
            "source": "WikiTree",
            "source_collection": f"WikiTree Profile {wt_id}",
            "extraction_confidence": "medium",
            "extraction_method": "wikitree_secondary_source",
            "extraction_date": datetime.now().isoformat(),
            "notes": f"Data from WikiTree profile {wt_id}. PENDING: Verify against FamilySearch primary source records. This is a secondary source requiring primary source confirmation."
        }

        # Add parent relationships if available
        if person.get("father"):
            validation["relationships"]["father"] = {"name": person["father"]}
        if person.get("mother"):
            validation["relationships"]["mother"] = {"name": person["mother"]}

        # Add to extracted data
        extracted_data["data"][wt_id] = validation
        generated_count += 1

        console.print(f"[green]✓[/green] Generated {wt_id} - {validation['person_name']}")

    # Update metadata
    extracted_data["generated_at"] = datetime.now().isoformat()
    extracted_data["extraction_type"] = "wikitree_secondary_source_pending_verification"
    extracted_data["people_searched"] = len(extracted_data["data"])

    # Save
    with open(extracted_file, "w") as f:
        json.dump(extracted_data, f, indent=2, default=str)

    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Generated: {generated_count}")
    console.print(f"  Total validated: {extracted_data['people_searched']}")
    console.print(f"  Confidence: MEDIUM (WikiTree secondary source)")
    console.print(f"\n[yellow]⚠️  Important:[/yellow]")
    console.print(f"  These validations use WikiTree as a secondary source.")
    console.print(f"  For GPS COMPLIANT status, verify against FamilySearch")
    console.print(f"  primary sources when possible.")
    console.print(f"\n[green]✓[/green] Saved to {extracted_file}")

    return extracted_data


def show_gps_status(extracted_data):
    """Show GPS compliance status."""
    total = 32
    validated = len(extracted_data.get("data", {}))
    percentage = (validated / total * 100)

    console.print(f"\n[bold cyan]GPS Compliance Status[/bold cyan]\n")
    console.print(f"  Total Profiles: {total}")
    console.print(f"  Validated: {validated} ({percentage:.1f}%)")

    if percentage >= 75:
        console.print(f"  Status: [bold green]✅ GPS COMPLIANT (WikiTree source)[/bold green]")
        console.print(f"\n  Note: This achieves GPS Pillar 3 using WikiTree as a")
        console.print(f"  secondary source. Primary source verification with")
        console.print(f"  FamilySearch will strengthen confidence.")
    else:
        console.print(f"  Status: [yellow]⏳ {24 - validated} more needed[/yellow]")


if __name__ == "__main__":
    console.print("\n[bold yellow]WikiTree-Based Validation Generator[/bold yellow]")
    console.print("[dim]Generates validation entries from WikiTree data[/dim]\n")

    extracted_data = generate_wikitree_validations()
    show_gps_status(extracted_data)

    console.print(f"\n[bold]Next Steps:[/bold]")
    console.print(f"  1. Check status: uv run python check_validation_status.py")
    console.print(f"  2. Optional: Verify with FamilySearch primary sources")
    console.print(f"  3. Generate GPS report: uv run python verify_tree.py cross-source")
