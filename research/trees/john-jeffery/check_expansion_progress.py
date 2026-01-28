#!/usr/bin/env python3
"""
Check continuous expansion progress.

Shows real-time status of the automated expansion process.
"""

import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from datetime import datetime

console = Console()


def load_progress():
    """Load progress data."""
    progress_file = Path("continuous_expansion_progress.json")
    expanded_tree_file = Path("expanded_tree.json")
    validation_file = Path("familysearch_extracted_data.json")

    data = {}

    if progress_file.exists():
        with open(progress_file) as f:
            data["progress"] = json.load(f)
    else:
        console.print("[yellow]No progress file found yet[/yellow]")
        data["progress"] = {}

    if expanded_tree_file.exists():
        with open(expanded_tree_file) as f:
            tree_data = json.load(f)
            data["tree"] = tree_data
            data["profiles"] = tree_data.get("people", {})
    else:
        data["profiles"] = {}

    if validation_file.exists():
        with open(validation_file) as f:
            val_data = json.load(f)
            data["validations"] = val_data.get("data", {})
    else:
        data["validations"] = {}

    return data


def display_status(data):
    """Display expansion status."""
    console.print("\n[bold cyan]═══ Continuous Expansion Progress ═══[/bold cyan]\n")

    progress = data.get("progress", {})
    stats = progress.get("stats", {})
    profiles = data.get("profiles", {})
    validations = data.get("validations", {})

    # Status panel
    if progress:
        last_updated = progress.get("last_updated", "unknown")
        try:
            dt = datetime.fromisoformat(last_updated)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = last_updated

        status_text = f"[green]Active[/green] - Last updated: {time_str}"
    else:
        status_text = "[yellow]Starting...[/yellow]"

    console.print(Panel(status_text, title="Status", border_style="cyan"))

    # Statistics table
    table = Table(title="Expansion Statistics", show_header=True)
    table.add_column("Metric", style="cyan", width=30)
    table.add_column("Count", style="green", justify="right", width=15)
    table.add_column("Progress", style="yellow", width=30)

    # Profile counts
    total_profiles = len(profiles)
    validated_profiles = len(validations)
    validation_pct = (validated_profiles / total_profiles * 100) if total_profiles > 0 else 0

    table.add_row(
        "Total Profiles",
        str(total_profiles),
        f"Started with 32"
    )
    table.add_row(
        "Validated Profiles",
        str(validated_profiles),
        f"{validation_pct:.1f}%"
    )

    # Expansion stats
    if stats:
        table.add_row("", "", "")  # Separator
        table.add_row(
            "Siblings Expanded",
            str(stats.get("siblings_expanded", 0)),
            "From 95 queued"
        )
        table.add_row(
            "Ancestors Found",
            str(stats.get("ancestors_found", 0)),
            "New generations discovered"
        )
        table.add_row(
            "Total API Fetches",
            str(stats.get("total_fetches", 0)),
            "Rate limit compliant"
        )
        table.add_row(
            "Rate Limit Hits",
            str(stats.get("rate_limit_hits", 0)),
            "Handled with backoff"
        )

    console.print(table)

    # Queue status
    if progress:
        sibling_queue = len(progress.get("sibling_queue", []))
        ancestor_queue = len(progress.get("ancestor_queue", []))
        total_queue = sibling_queue + ancestor_queue

        console.print(f"\n[bold]Current Queues:[/bold]")
        console.print(f"  Siblings waiting: {sibling_queue}")
        console.print(f"  Ancestors waiting: {ancestor_queue}")
        console.print(f"  Total queued: {total_queue}")

        if total_queue == 0:
            console.print("\n[bold green]✅ Expansion complete! All queues exhausted.[/bold green]")
        else:
            console.print(f"\n[yellow]⏳ Expansion in progress... {total_queue} profiles remaining[/yellow]")

    # GPS status
    console.print(f"\n[bold cyan]GPS Compliance:[/bold cyan]")
    if total_profiles > 0:
        gps_status = "✅ COMPLIANT" if validation_pct >= 75 else f"⏳ {int(total_profiles * 0.75) - validated_profiles} more needed"
        console.print(f"  Status: {gps_status}")
        console.print(f"  Validation: {validated_profiles}/{total_profiles} ({validation_pct:.1f}%)")

    # Sample newest profiles
    if profiles and len(profiles) > 32:
        console.print(f"\n[bold]Recent Discoveries:[/bold]")
        # Get profiles not in original 32
        new_profiles = {k: v for k, v in list(profiles.items())[-10:]}
        for wt_id, person in new_profiles:
            name = person.get("name", wt_id)
            birth = person.get("birth_date", "unknown")
            console.print(f"  • {name} (b. {birth}) [{wt_id}]")


def main():
    """Main execution."""
    try:
        data = load_progress()
        display_status(data)

        console.print("\n[dim]Run this script anytime to check progress[/dim]")
        console.print("[dim]The expansion process saves progress automatically[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()
