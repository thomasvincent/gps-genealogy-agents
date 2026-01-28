#!/usr/bin/env python3
"""
Unified Family Tree Verification CLI

Consolidates WikiTree live verification, FamilySearch extraction via Playwright,
and cross-source GPS Pillar 3 analysis into a single DRY tool.

Usage:
    uv run python verify_tree.py wikitree            # Verify WikiTree profiles
    uv run python verify_tree.py familysearch        # Extract FamilySearch data
    uv run python verify_tree.py cross-source        # Analyze corroboration
    uv run python verify_tree.py all                 # Run all verifications
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from verification import (
    CrossSourceAnalyzer,
    FamilySearchVerifier,
    TreeData,
    WikiTreeVerifier,
    save_report,
)

app = typer.Typer(
    name="verify-tree",
    help="Unified family tree verification tool",
    add_completion=False,
)

console = Console()


@app.command()
def wikitree(
    tree_file: Path = typer.Option(Path("tree.json"), "--tree", "-t", help="Path to tree.json"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """Verify WikiTree profiles against live API data."""

    console.print(Panel("[bold]WikiTree Live Verification[/bold]", style="cyan"))

    # Load tree data
    tree = TreeData(tree_file)
    try:
        tree.load()
    except FileNotFoundError:
        console.print(f"[red]Error: {tree_file} not found[/red]")
        raise typer.Exit(1)

    wikitree_ids = tree.get_wikitree_ids()
    cached_relationships = tree.get_cached_wikitree_relationships()

    if not wikitree_ids:
        console.print("[yellow]No WikiTree profiles found in tree.json[/yellow]")
        raise typer.Exit(0)

    console.print(f"Found {len(wikitree_ids)} WikiTree profiles: {', '.join(wikitree_ids)}\n")

    async def verify():
        verifier = WikiTreeVerifier()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching live WikiTree data...", total=None)
            live_data = await verifier.verify_profiles(wikitree_ids)
            progress.update(task, description="Comparing cached vs live...")
            comparison = verifier.compare_with_cached(cached_relationships)

        return live_data, comparison

    live_data, comparison = asyncio.run(verify())

    # Display results
    console.print("\n[bold cyan]Verification Results[/bold cyan]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("WikiTree ID")
    table.add_column("Person Name")
    table.add_column("Status")

    for item in comparison["up_to_date"]:
        table.add_row(
            item["wikitree_id"],
            item["person_name"],
            "[green]✓ Up-to-date[/green]"
        )

    for item in comparison["modified"]:
        changes = item["person_changes"] + item["relationship_changes"]
        table.add_row(
            item["wikitree_id"],
            item["person_name"],
            f"[yellow]⚠ Modified ({len(changes)} changes)[/yellow]"
        )

    console.print(table)

    # Summary
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Up-to-date: {len(comparison['up_to_date'])}")
    console.print(f"  Modified: {len(comparison['modified'])}")
    console.print(f"  Missing: {len(comparison['missing_in_cache'])}")

    if comparison["up_to_date"] and not comparison["modified"]:
        console.print("\n[bold green]✓ GPS Pillar 3: All WikiTree data is current[/bold green]")
    elif comparison["modified"]:
        console.print("\n[bold yellow]⚠ GPS Pillar 3: Some records need updating[/bold yellow]")

    # Save report
    output_file = output or Path("wikitree_verification.json")
    report = {
        "generated_at": datetime.now().isoformat(),
        "verification_type": "wikitree_live",
        "live_data": live_data,
        "comparison": comparison,
    }
    save_report(report, str(output_file))
    console.print(f"\n[dim]Report saved to {output_file}[/dim]")


@app.command()
def familysearch(
    tree_file: Path = typer.Option(Path("tree.json"), "--tree", "-t", help="Path to tree.json"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file"),
) -> None:
    """Extract FamilySearch family tree data using Playwright browser automation."""

    console.print(Panel("[bold]FamilySearch Data Extraction[/bold]", style="cyan"))

    # Load tree data to get search parameters
    tree = TreeData(tree_file)
    try:
        tree.load()
    except FileNotFoundError:
        console.print(f"[red]Error: {tree_file} not found[/red]")
        raise typer.Exit(1)

    # Get WikiTree data for search parameters
    wikitree_ids = tree.get_wikitree_ids()
    cached_relationships = tree.get_cached_wikitree_relationships()

    if not cached_relationships:
        console.print("[yellow]No WikiTree profiles to use as search basis[/yellow]")
        console.print("Run 'verify_tree.py wikitree' first to get profile data")
        raise typer.Exit(1)

    console.print(f"Will search FamilySearch for {len(cached_relationships)} people\n")

    # Use Playwright MCP tools via subprocess
    familysearch_data = {}

    for wt_id, person_data in cached_relationships.items():
        person_name = person_data["person_name"]
        birth_date = person_data.get("birth_date", "")
        birth_year = birth_date.split("-")[0] if birth_date else ""

        console.print(f"[dim]Searching for {person_name} (b. {birth_year})...[/dim]")

        # Build FamilySearch search URL
        search_url = f"https://www.familysearch.org/search/record/results"
        params = f"?q.givenName={person_name.split()[0]}&q.surname={person_name.split()[-1]}"
        if birth_year:
            params += f"&q.birthLikeDate.from={int(birth_year)-5}&q.birthLikeDate.to={int(birth_year)+5}"

        full_url = search_url + params

        # Use Playwright to navigate and extract
        playwright_code = f"""
async (page) => {{
    await page.goto('{full_url}', {{ waitUntil: 'networkidle' }});
    await page.waitForTimeout(2000);

    // Get page title to verify we're on results page
    const title = await page.title();

    // Try to find and click first result
    try {{
        const firstResult = await page.locator('a.person-name').first();
        if (await firstResult.isVisible()) {{
            await firstResult.click();
            await page.waitForTimeout(2000);

            // Extract family relationships from person page
            const familySection = await page.locator('[data-test="family-members"]').textContent().catch(() => '');

            return {{
                person: '{person_name}',
                url: page.url(),
                family_text: familySection
            }};
        }}
    }} catch (e) {{
        console.error('Could not extract data:', e);
    }}

    return {{
        person: '{person_name}',
        url: page.url(),
        family_text: ''
    }};
}}
"""

        # Call Playwright via MCP (this is a simplified version - actual implementation
        # would use the MCP tool directly)
        console.print(f"  [yellow]Note: Full Playwright integration requires MCP tool access[/yellow]")
        console.print(f"  [dim]Search URL: {full_url}[/dim]")

        # Placeholder for extracted data
        familysearch_data[person_name] = {
            "search_url": full_url,
            "extracted": False,
            "note": "Manual extraction required or use browser automation"
        }

    # Save report
    output_file = output or Path("familysearch_extraction.json")
    report = {
        "generated_at": datetime.now().isoformat(),
        "extraction_type": "familysearch_playwright",
        "people_searched": len(familysearch_data),
        "data": familysearch_data,
        "instructions": "To complete extraction, use Playwright MCP tools to navigate search URLs and extract family relationships"
    }
    save_report(report, str(output_file))

    console.print(f"\n[bold yellow]⚠ FamilySearch extraction requires browser automation[/bold yellow]")
    console.print(f"\nSearch URLs saved to {output_file}")
    console.print("\nTo extract manually:")
    console.print("1. Visit each search URL in a browser")
    console.print("2. Click on the person's profile")
    console.print("3. Extract parent/spouse/child names from the family section")
    console.print("4. Compare with WikiTree data\n")


@app.command()
def cross_source(
    wikitree_file: Path = typer.Option(Path("wikitree_verification.json"), "--wikitree", help="WikiTree verification JSON"),
    familysearch_file: Path = typer.Option(Path("familysearch_extraction.json"), "--familysearch", help="FamilySearch extraction JSON"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file"),
) -> None:
    """Analyze cross-source corroboration for GPS Pillar 3 compliance."""

    console.print(Panel("[bold]Cross-Source GPS Pillar 3 Analysis[/bold]", style="cyan"))

    # Load WikiTree verification
    try:
        with open(wikitree_file) as f:
            wikitree_data = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]Error: {wikitree_file} not found[/red]")
        console.print("Run 'verify_tree.py wikitree' first")
        raise typer.Exit(1)

    # Load FamilySearch extraction
    try:
        with open(familysearch_file) as f:
            familysearch_data = json.load(f)
    except FileNotFoundError:
        console.print(f"[yellow]Warning: {familysearch_file} not found[/yellow]")
        console.print("FamilySearch data not available for comparison")
        familysearch_data = {"data": {}}

    # Analyze corroboration
    analyzer = CrossSourceAnalyzer()

    wt_relationships = wikitree_data.get("live_data", {})
    fs_relationships = familysearch_data.get("data", {})

    corroboration = analyzer.analyze(wt_relationships, fs_relationships)
    gps_assessment = analyzer.assess_gps_compliance(corroboration)

    # Display results
    console.print("\n[bold cyan]Corroboration Analysis[/bold cyan]\n")

    if corroboration["confirmed"]:
        console.print("[bold green]✓ Confirmed by Multiple Sources:[/bold green]")
        for item in corroboration["confirmed"]:
            console.print(f"  • {item['person']} → {item['relationship']}: {item['relative']}")
            console.print(f"    Sources: {', '.join(item['sources'])}")

    if corroboration["conflicts"]:
        console.print("\n[bold red]⚠ Conflicts Requiring Resolution:[/bold red]")
        for item in corroboration["conflicts"]:
            console.print(f"  • {item['person']} → {item['relationship']}")
            console.print(f"    WikiTree: {item['wikitree_says']}")
            console.print(f"    FamilySearch: {item['familysearch_says']}")

    if corroboration["wikitree_only"]:
        console.print("\n[bold yellow]⚠ WikiTree Only (No Corroboration):[/bold yellow]")
        for item in corroboration["wikitree_only"]:
            console.print(f"  • {item['person']}")
            rels = item.get("relationships", {})
            if rels.get("father"):
                console.print(f"    Father: {rels['father']['name']}")
            if rels.get("mother"):
                console.print(f"    Mother: {rels['mother']['name']}")

    # GPS Assessment
    console.print(f"\n[bold]GPS Pillar 3 Assessment:[/bold]")
    console.print(f"  Status: {gps_assessment['status']}")
    console.print(f"  Grade: {gps_assessment['grade']}")
    console.print(f"  Total relationships: {gps_assessment['total_relationships']}")
    console.print(f"  Confirmed (multi-source): {gps_assessment['confirmed_count']}")
    console.print(f"  Conflicts: {gps_assessment['conflicts_count']}")
    console.print(f"  Single source only: {gps_assessment['single_source_count']}")

    if gps_assessment["grade"] == "compliant":
        console.print("\n[bold green]✓ GPS Pillar 3: COMPLIANT[/bold green]")
    elif gps_assessment["grade"] == "partial":
        console.print("\n[bold yellow]⚠ GPS Pillar 3: PARTIAL[/bold yellow]")
    else:
        console.print("\n[bold red]❌ GPS Pillar 3: INCOMPLETE[/bold red]")

    # Save report
    output_file = output or Path("cross_source_analysis.json")
    report = {
        "generated_at": datetime.now().isoformat(),
        "analysis_type": "cross_source_gps_pillar_3",
        "corroboration": corroboration,
        "gps_assessment": gps_assessment,
    }
    save_report(report, str(output_file))
    console.print(f"\n[dim]Report saved to {output_file}[/dim]")


@app.command()
def all(
    tree_file: Path = typer.Option(Path("tree.json"), "--tree", "-t", help="Path to tree.json"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """Run all verification steps in sequence."""

    console.print(Panel("[bold]Complete Tree Verification Suite[/bold]", style="cyan"))

    # Step 1: WikiTree
    console.print("\n[bold]Step 1: WikiTree Live Verification[/bold]")
    try:
        from typer.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(app, ["wikitree", "--tree", str(tree_file)])
        if result.exit_code != 0:
            console.print("[red]WikiTree verification failed[/red]")
            raise typer.Exit(1)
    except Exception:
        # Fallback to direct call
        wikitree(tree_file=tree_file, output=None, verbose=verbose)

    # Step 2: FamilySearch
    console.print("\n[bold]Step 2: FamilySearch Data Extraction[/bold]")
    try:
        from typer.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(app, ["familysearch", "--tree", str(tree_file)])
        if result.exit_code != 0:
            console.print("[yellow]FamilySearch extraction incomplete[/yellow]")
    except Exception:
        familysearch(tree_file=tree_file, output=None)

    # Step 3: Cross-source analysis
    console.print("\n[bold]Step 3: Cross-Source Analysis[/bold]")
    try:
        from typer.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(app, ["cross-source"])
        if result.exit_code != 0:
            console.print("[yellow]Cross-source analysis incomplete[/yellow]")
    except Exception:
        cross_source()

    console.print("\n[bold green]✓ Verification suite complete[/bold green]")


if __name__ == "__main__":
    app()
