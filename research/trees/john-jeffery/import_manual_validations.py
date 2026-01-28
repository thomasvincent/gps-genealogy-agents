#!/usr/bin/env python3
"""
Import manually completed validation data into familysearch_extracted_data.json.

Usage:
    uv run python import_manual_validations.py [batch_file.json]

Default: Imports from manual_validation_batch_tier1.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


def load_batch_file(batch_file: Path) -> dict:
    """Load manual validation batch file."""
    if not batch_file.exists():
        console.print(f"[red]Error: {batch_file} not found[/red]")
        sys.exit(1)

    with open(batch_file) as f:
        return json.load(f)


def load_extracted_data(extracted_file: Path) -> dict:
    """Load existing extracted data."""
    if extracted_file.exists():
        with open(extracted_file) as f:
            return json.load(f)
    else:
        return {
            "generated_at": datetime.now().isoformat(),
            "extraction_type": "familysearch_mixed_extraction",
            "people_searched": 0,
            "data": {}
        }


def validate_entry(profile: dict) -> bool:
    """Check if a profile entry has been filled in."""
    fs_data = profile.get("familysearch_data", {})

    # Check if key fields are filled
    required_fields = ["person_name", "birth_date", "birth_location"]
    for field in required_fields:
        if not fs_data.get(field) or fs_data.get(field) == "":
            return False

    return True


def import_validations(batch_file: Path, extracted_file: Path) -> int:
    """Import completed validations."""
    batch_data = load_batch_file(batch_file)
    extracted_data = load_extracted_data(extracted_file)

    if "data" not in extracted_data:
        extracted_data["data"] = {}

    imported_count = 0
    skipped_count = 0

    console.print(f"\n[bold cyan]Importing validations from {batch_file}[/bold cyan]\n")

    for profile in batch_data.get("profiles", []):
        wt_id = profile["wikitree_id"]

        # Skip if already in extracted data
        if wt_id in extracted_data["data"]:
            console.print(f"[yellow]Skipping {wt_id} - already validated[/yellow]")
            skipped_count += 1
            continue

        # Check if filled in
        if not validate_entry(profile):
            console.print(f"[dim]Skipping {wt_id} - not filled in[/dim]")
            skipped_count += 1
            continue

        # Import the data
        fs_data = profile["familysearch_data"]
        fs_data["wikitree_id"] = wt_id
        fs_data["extraction_date"] = datetime.now().isoformat()

        extracted_data["data"][wt_id] = fs_data
        imported_count += 1

        console.print(f"[green]✓[/green] Imported {wt_id} - {fs_data['person_name']}")

    # Update metadata
    extracted_data["generated_at"] = datetime.now().isoformat()
    extracted_data["people_searched"] = len(extracted_data["data"])

    # Save
    with open(extracted_file, "w") as f:
        json.dump(extracted_data, f, indent=2, default=str)

    console.print(f"\n[bold]Import Summary:[/bold]")
    console.print(f"  Imported: {imported_count}")
    console.print(f"  Skipped: {skipped_count}")
    console.print(f"  Total validated: {extracted_data['people_searched']}")
    console.print(f"\n[green]✓[/green] Saved to {extracted_file}")

    return imported_count


def show_completion_status(extracted_file: Path):
    """Show GPS compliance status."""
    extracted_data = load_extracted_data(extracted_file)
    total_profiles = 32  # Known from expanded_tree.json
    validated_count = len(extracted_data.get("data", {}))
    percentage = (validated_count / total_profiles * 100)

    console.print(f"\n[bold cyan]GPS Compliance Status[/bold cyan]\n")

    # Create progress table
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Profiles", str(total_profiles))
    table.add_row("Validated", str(validated_count))
    table.add_row("Remaining", str(total_profiles - validated_count))
    table.add_row("Percentage", f"{percentage:.1f}%")

    # Determine GPS status
    if percentage >= 75:
        status = "[bold green]✅ GPS COMPLIANT[/bold green]"
    else:
        needed = 24 - validated_count
        status = f"[yellow]⏳ Need {needed} more for COMPLIANT[/yellow]"

    table.add_row("GPS Status", status)

    console.print(table)


def main():
    """Main execution."""
    # Get batch file from command line or use default
    if len(sys.argv) > 1:
        batch_file = Path(sys.argv[1])
    else:
        batch_file = Path("manual_validation_batch_tier1.json")

    extracted_file = Path("familysearch_extracted_data.json")

    console.print(f"\n[bold yellow]Manual Validation Import[/bold yellow]\n")

    imported = import_validations(batch_file, extracted_file)

    if imported > 0:
        show_completion_status(extracted_file)

        console.print(f"\n[bold]Next Steps:[/bold]")
        if Path("familysearch_extracted_data.json").exists():
            with open("familysearch_extracted_data.json") as f:
                data = json.load(f)
                validated_count = len(data.get("data", {}))

                if validated_count < 24:
                    console.print(f"Continue validating - need {24 - validated_count} more for GPS COMPLIANT")
                    console.print(f"Next tier: manual_validation_batch_tier2.json")
                elif validated_count < 27:
                    console.print(f"🎯 You're GPS COMPLIANT! Consider validating {27 - validated_count} more for 84% coverage")
                else:
                    console.print("🎉 Excellent coverage! Consider completing all 32 for 100%")
    else:
        console.print("\n[yellow]No new validations imported.[/yellow]")
        console.print("Make sure to fill in the familysearch_data fields in the batch file.")


if __name__ == "__main__":
    main()
