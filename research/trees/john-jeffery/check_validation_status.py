#!/usr/bin/env python3
"""Quick status checker for validation progress."""

import json
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


def main():
    """Check validation status."""
    extracted_file = Path("familysearch_extracted_data.json")

    if not extracted_file.exists():
        console.print("[red]No validation data found[/red]")
        return

    with open(extracted_file) as f:
        data = json.load(f)

    total = 32
    validated = len(data.get("data", {}))
    remaining = total - validated
    percentage = (validated / total * 100)

    console.print("\n[bold cyan]═══ Validation Status ═══[/bold cyan]\n")

    # Progress bar
    bars = int(percentage / 2)  # 50 chars = 100%
    progress_bar = "█" * bars + "░" * (50 - bars)
    console.print(f"[green]{progress_bar}[/green] {percentage:.1f}%\n")

    # Status table
    table = Table(show_header=False, box=None)
    table.add_column("Label", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Total Profiles", str(total))
    table.add_row("Validated", f"[green]{validated}[/green]")
    table.add_row("Remaining", f"[yellow]{remaining}[/yellow]")

    # GPS status
    if percentage >= 75:
        gps_status = "[bold green]✅ GPS COMPLIANT[/bold green]"
    else:
        needed = 24 - validated
        gps_status = f"[yellow]⏳ Need {needed} more[/yellow]"

    table.add_row("GPS Status", gps_status)

    console.print(table)

    # Show validated profiles
    if validated > 0:
        console.print(f"\n[bold]Validated Profiles ({validated}):[/bold]")
        for wt_id in sorted(data.get("data", {}).keys()):
            profile = data["data"][wt_id]
            name = profile.get("person_name", wt_id)
            birth_year = profile.get("birth_date", "").split("-")[0] if profile.get("birth_date") else "?"
            console.print(f"  [green]✓[/green] {wt_id} - {name} (b. {birth_year})")

    # Next steps
    console.print(f"\n[bold]Next Steps:[/bold]")
    if percentage < 28:
        console.print("  1. Open manual_validation_batch_tier1.json")
        console.print("  2. Fill in FamilySearch data for 6 profiles")
        console.print("  3. Run: uv run python import_manual_validations.py")
    elif percentage < 66:
        console.print("  1. Open manual_validation_batch_tier2.json")
        console.print("  2. Continue validating")
    elif percentage < 75:
        console.print("  1. Open manual_validation_batch_tier3.json")
        console.print("  2. Complete for GPS COMPLIANT status")
    else:
        console.print("  🎉 GPS COMPLIANT! Optionally complete remaining profiles")

    console.print()


if __name__ == "__main__":
    main()
