"""CLI interface for GPS Genealogy Agents."""

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(
    name="gps-agents",
    help="GPS Genealogical Research Multi-Agent System",
    add_completion=False,
)
console = Console()


def get_config():
    """Load configuration from environment."""
    from dotenv import load_dotenv
    import os

    load_dotenv()

    return {
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "rocksdb_path": os.getenv("ROCKSDB_PATH", "./data/ledger"),
        "sqlite_path": os.getenv("SQLITE_PATH", "./data/projection.db"),
        "familysearch_client_id": os.getenv("FAMILYSEARCH_CLIENT_ID"),
        "familysearch_client_secret": os.getenv("FAMILYSEARCH_CLIENT_SECRET"),
    }


def get_sources(config: dict):
    """Initialize data sources based on configuration."""
    from .sources.accessgenealogy import AccessGenealogySource
    from .sources.familysearch import FamilySearchSource
    from .sources.jerripedia import JerripediaSource
    from .sources.wikitree import WikiTreeSource

    sources = [
        WikiTreeSource(),  # Free, no auth needed
        AccessGenealogySource(),  # Free, scraping
        JerripediaSource(),  # Free, API
    ]

    # Add FamilySearch if configured
    if config.get("familysearch_client_id"):
        sources.append(
            FamilySearchSource(
                client_id=config["familysearch_client_id"],
                client_secret=config["familysearch_client_secret"],
            )
        )

    return sources


@app.command()
def research(
    query: str = typer.Argument(..., help="Research query in natural language"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file for results"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """Run a genealogical research query."""
    config = get_config()

    if not config.get("anthropic_api_key") and not config.get("openai_api_key"):
        console.print("[red]Error: No API keys configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.[/red]")
        raise typer.Exit(1)

    console.print(Panel(f"[bold]Research Query:[/bold] {query}", title="GPS Genealogy Research"))

    async def run():
        from .graph import run_research
        from .ledger.fact_ledger import FactLedger
        from .projections.sqlite_projection import SQLiteProjection

        # Initialize storage
        ledger = FactLedger(config["rocksdb_path"])
        projection = SQLiteProjection(config["sqlite_path"])
        sources = get_sources(config)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Researching...", total=None)

            result = await run_research(
                task=query,
                ledger=ledger,
                projection=projection,
                sources=sources,
            )

            progress.update(task, completed=True)

        return result

    result = asyncio.run(run())

    # Display results
    _display_results(result, verbose)

    # Save to file if requested
    if output:
        _save_results(result, output)
        console.print(f"[green]Results saved to {output}[/green]")


@app.command()
def load_gedcom(
    file_path: Path = typer.Argument(..., help="Path to GEDCOM file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """Load a GEDCOM file into the system."""
    from .sources.gedcom import GedcomSource

    if not file_path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    source = GedcomSource(file_path)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading GEDCOM...", total=None)
        count = source.load_file()
        progress.update(task, completed=True)

    console.print(f"[green]Loaded {count} individuals from {file_path.name}[/green]")

    if verbose:
        # Show sample individuals
        table = Table(title="Sample Individuals")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Birth")
        table.add_column("Death")

        for i, (indi_id, indi) in enumerate(list(source._individuals.items())[:10]):
            table.add_row(
                indi_id,
                indi.get("name", "").replace("/", ""),
                indi.get("birth_date", ""),
                indi.get("death_date", ""),
            )

        console.print(table)


@app.command("facts")
def list_facts(
    status: str = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results"),
):
    """List facts from the ledger."""
    config = get_config()

    from .ledger.fact_ledger import FactLedger
    from .models.fact import FactStatus

    ledger = FactLedger(config["rocksdb_path"])

    status_filter = None
    if status:
        try:
            status_filter = FactStatus(status.lower())
        except ValueError:
            console.print(f"[red]Invalid status. Choose from: {[s.value for s in FactStatus]}[/red]")
            raise typer.Exit(1)

    table = Table(title="Facts")
    table.add_column("ID", style="dim")
    table.add_column("Statement")
    table.add_column("Status")
    table.add_column("Confidence")
    table.add_column("Sources")

    count = 0
    for fact in ledger.iter_all_facts(status_filter):
        if count >= limit:
            break
        table.add_row(
            str(fact.fact_id)[:8] + "...",
            fact.statement[:50] + "..." if len(fact.statement) > 50 else fact.statement,
            fact.status.value,
            f"{fact.confidence_score:.2f}",
            str(len(fact.sources)),
        )
        count += 1

    console.print(table)
    console.print(f"[dim]Showing {count} facts[/dim]")


@app.command()
def stats():
    """Show statistics about the research database."""
    config = get_config()

    from .projections.sqlite_projection import SQLiteProjection

    projection = SQLiteProjection(config["sqlite_path"])
    statistics = projection.get_statistics()

    table = Table(title="Database Statistics")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Total Facts", str(statistics.get("total_facts", 0)))
    table.add_row("Accepted", str(statistics.get("count_accepted", 0)))
    table.add_row("Proposed", str(statistics.get("count_proposed", 0)))
    table.add_row("Incomplete", str(statistics.get("count_incomplete", 0)))
    table.add_row("Rejected", str(statistics.get("count_rejected", 0)))
    table.add_row(
        "Avg Confidence (Accepted)",
        f"{statistics.get('avg_confidence_accepted', 0):.2f}",
    )

    console.print(table)

    # Sources breakdown
    sources = statistics.get("sources", {})
    if sources:
        source_table = Table(title="Records by Source")
        source_table.add_column("Source")
        source_table.add_column("Count")

        for source, count in sorted(sources.items(), key=lambda x: -x[1]):
            source_table.add_row(source, str(count))

        console.print(source_table)


@app.command()
def search(
    term: str = typer.Argument(..., help="Search term"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results"),
):
    """Search fact statements."""
    config = get_config()

    from .projections.sqlite_projection import SQLiteProjection

    projection = SQLiteProjection(config["sqlite_path"])
    facts = projection.search_statements(term, limit)

    if not facts:
        console.print(f"[yellow]No facts found matching '{term}'[/yellow]")
        return

    table = Table(title=f"Search Results for '{term}'")
    table.add_column("Statement")
    table.add_column("Status")
    table.add_column("Confidence")

    for fact in facts:
        table.add_row(
            fact.statement,
            fact.status.value,
            f"{fact.confidence_score:.2f}",
        )

    console.print(table)


def _display_results(result: dict, verbose: bool):
    """Display research results."""
    # Synthesis
    synthesis = result.get("synthesis", {})

    if synthesis.get("proof_summary"):
        console.print(Panel(synthesis["proof_summary"], title="[bold]Proof Summary[/bold]"))

    if synthesis.get("narrative"):
        console.print(Panel(synthesis["narrative"], title="[bold]Narrative[/bold]"))

    # Accepted facts
    accepted = result.get("accepted_facts", [])
    if accepted:
        table = Table(title="Accepted Facts")
        table.add_column("Statement")
        table.add_column("Confidence")
        table.add_column("Sources")

        for fact in accepted:
            table.add_row(
                fact.statement,
                f"{fact.confidence_score:.2f}",
                str(len(fact.sources)),
            )

        console.print(table)

    # Open questions
    open_questions = synthesis.get("open_questions", [])
    if open_questions:
        console.print("\n[bold]Open Questions:[/bold]")
        for q in open_questions:
            console.print(f"  • {q}")

    # Sources searched
    sources = result.get("sources_searched", [])
    if sources and verbose:
        console.print(f"\n[dim]Sources searched: {', '.join(sources)}[/dim]")


def _save_results(result: dict, output: Path):
    """Save results to file."""

    def serialize(obj):
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    output_data = {
        "task": result.get("task"),
        "synthesis": result.get("synthesis"),
        "accepted_facts": [
            serialize(f) for f in result.get("accepted_facts", [])
        ],
        "sources_searched": result.get("sources_searched"),
    }

    with open(output, "w") as f:
        json.dump(output_data, f, indent=2, default=str)


if __name__ == "__main__":
    app()
