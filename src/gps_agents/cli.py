"""CLI interface for GPS Genealogy Agents using Semantic Kernel + AutoGen."""
from __future__ import annotations

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
    help="GPS Genealogical Research Multi-Agent System (SK + AutoGen)",
    add_completion=False,
)

backfill_app = typer.Typer(help="Backfill utilities")
app.add_typer(backfill_app, name="backfill")

plan_app = typer.Typer(help="Dry-run planners (decision-only)")
app.add_typer(plan_app, name="plan")
console = Console()


def get_config():
    """Load configuration from environment."""
    import os

    from dotenv import load_dotenv

    load_dotenv()

    return {
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "data_dir": Path(os.getenv("DATA_DIR", "./data")),
        "familysearch_client_id": os.getenv("FAMILYSEARCH_CLIENT_ID"),
        "familysearch_client_secret": os.getenv("FAMILYSEARCH_CLIENT_SECRET"),
    }


def get_kernel_config():
    """Create SK kernel configuration."""
    from gps_agents.sk.kernel import KernelConfig

    config = get_config()
    return KernelConfig(
        data_dir=config["data_dir"],
        openai_api_key=config["openai_api_key"],
        anthropic_api_key=config["anthropic_api_key"],
    )


@app.command()
def research(
    query: str = typer.Argument(..., help="Research query in natural language"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file for results"),  # noqa: B008
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    max_rounds: int = typer.Option(50, "--max-rounds", "-r", help="Maximum conversation rounds"),
    run_id: str = typer.Option(None, "--run-id", help="Bind run_id to structured logs"),
) -> None:
    """Run a genealogical research query using the GPS multi-agent system."""
    config = get_config()
    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)

    if not config.get("anthropic_api_key") and not config.get("openai_api_key"):
        console.print("[red]Error: No API keys configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.[/red]")
        raise typer.Exit(1)

    console.print(Panel(f"[bold]Research Query:[/bold] {query}", title="GPS Genealogy Research"))

    async def run():
        from gps_agents.autogen.orchestration import run_research_session

        kernel_config = get_kernel_config()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Researching with GPS agents...", total=None)

            result = await run_research_session(
                query=query,
                kernel_config=kernel_config,
                max_rounds=max_rounds,
            )

            progress.update(task, completed=True)

        return result

    result = asyncio.run(run())

    # Display results
    _display_chat_results(result, verbose)

    # Save to file if requested
    if output:
        _save_results(result, output)
        console.print(f"[green]Results saved to {output}[/green]")


@app.command()
def evaluate(
    fact_id: str = typer.Argument(..., help="Fact UUID to evaluate"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """Evaluate a fact against GPS standards."""
    config = get_config()

    if not config.get("openai_api_key"):
        console.print("[red]Error: OPENAI_API_KEY required for GPS evaluation.[/red]")
        raise typer.Exit(1)

    async def run():
        from gps_agents.autogen.orchestration import evaluate_fact_gps
        from gps_agents.sk.kernel import create_kernel

        kernel_config = get_kernel_config()
        kernel = create_kernel(kernel_config)

        # Get fact from ledger
        ledger_plugin = kernel.get_plugin("ledger")
        fact_json = await ledger_plugin.get_fact(fact_id=fact_id)

        if "error" in fact_json:
            console.print(f"[red]Error: {fact_json}[/red]")
            raise typer.Exit(1)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Evaluating GPS pillars...", total=None)
            result = await evaluate_fact_gps(fact_json, kernel_config)
            progress.update(task, completed=True)

        return result

    result = asyncio.run(run())

    console.print(Panel("GPS Evaluation Complete", title="[bold]Evaluation Results[/bold]"))

    if verbose:
        for msg in result.get("evaluation", []):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            console.print(f"\n[bold]{role}:[/bold] {content[:500]}...")


@app.command()
def translate(
    text: str = typer.Argument(..., help="Text to translate"),
    language: str = typer.Option("auto", "--language", "-l", help="Source language"),
) -> None:
    """Translate a genealogical record."""
    config = get_config()

    if not config.get("openai_api_key"):
        console.print("[red]Error: OPENAI_API_KEY required.[/red]")
        raise typer.Exit(1)

    async def run():
        from gps_agents.autogen.orchestration import translate_record

        kernel_config = get_kernel_config()
        return await translate_record(text, language, kernel_config)

    result = asyncio.run(run())

    if result.get("translation"):
        console.print(Panel(result["translation"], title=f"[bold]Translation from {language}[/bold]"))
    else:
        console.print("[yellow]No translation returned[/yellow]")


@app.command()
def load_gedcom(
    file_path: Path = typer.Argument(..., help="Path to GEDCOM file"),  # noqa: B008
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """Load a GEDCOM file into the system."""
    from gps_agents.models.search import SearchQuery
    from gps_agents.sources.gedcom import GedcomSource

    if not file_path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    async def run():
        source = GedcomSource()
        count = source.load_file(str(file_path))
        records = await source.search(SearchQuery())
        return count, records

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading GEDCOM...", total=None)
        count, records = asyncio.run(run())
        progress.update(task, completed=True)

    console.print(f"[green]Loaded {count} individuals from {file_path.name}[/green]")

    if verbose and records:
        table = Table(title="Sample Individuals")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Source")

        for record in records[:10]:
            table.add_row(
                record.record_id,
                record.raw_data.get("name", "Unknown"),
                record.source_name,
            )

        console.print(table)


@app.command("facts")
def list_facts(
    status: str = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results"),
) -> None:
    """List facts from the ledger."""
    config = get_config()

    from gps_agents.ledger.fact_ledger import FactLedger
    from gps_agents.models.fact import FactStatus

    ledger = FactLedger(str(config["data_dir"] / "ledger"))

    status_filter = None
    if status:
        try:
            status_filter = FactStatus(status.upper())
        except ValueError as err:
            console.print(f"[red]Invalid status. Choose from: {[s.value for s in FactStatus]}[/red]")
            raise typer.Exit(1) from err

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

    ledger.close()


@plan_app.command("person")
def plan_person(
    given: str = typer.Option(..., "--given", help="Given name"),
    surname: str = typer.Option(..., "--surname", help="Surname"),
    run_id: str = typer.Option(None, "--run-id", help="Bind run_id"),
) -> None:
    """Decision-only plan for a Person upsert (no writes)."""
    from gps_agents.idempotency.decision import decide_upsert_person
    from gps_agents.gramps.models import Person as GPerson, Name as GName
    from gps_agents.projections.sqlite_projection import SQLiteProjection
    from gps_agents.gramps.client import GrampsClient
    import json as _json

    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)

    cfg = get_config()
    proj = SQLiteProjection(str(cfg["data_dir"] / "projection.db"))
    # For decision-only we don't need a real DB; create an in-memory client placeholder
    # but GrampsClient expects a path; we provide a non-existent path and only use matcher lightly.
    # In practice, matcher may need candidates; here it will return create unless a fingerprint exists.
    gc = GrampsClient(cfg["data_dir"])  # not connecting

    p = GPerson(names=[GName(given=given, surname=surname)])
    dec = decide_upsert_person(gc, proj, p)
console.print(_json.dumps(dec.__dict__, indent=2))


@plan_app.command("event")
def plan_event(
    event_type: str = typer.Option(..., "--type", help="Event type e.g., birth"),
    year: int = typer.Option(None, "--year", help="Year"),
    run_id: str = typer.Option(None, "--run-id", help="Bind run_id"),
) -> None:
    from gps_agents.idempotency.decision import decide_upsert_event
    from gps_agents.gramps.models import Event as GEvent, EventType as GEventType, GrampsDate
    from gps_agents.projections.sqlite_projection import SQLiteProjection
    from gps_agents.gramps.client import GrampsClient
    import json as _json

    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)

    cfg = get_config()
    proj = SQLiteProjection(str(cfg["data_dir"] / "projection.db"))
    gc = GrampsClient(cfg["data_dir"])  # not connecting

    et = GEventType(event_type) if event_type in GEventType.__members__.values() else GEventType.OTHER
    ev = GEvent(event_type=et, date=GrampsDate(year=year) if year else None)
    dec = decide_upsert_event(gc, proj, ev)
    console.print(_json.dumps(dec.__dict__, indent=2))


@plan_app.command("source")
def plan_source(
    title: str = typer.Option(..., "--title", help="Source title"),
    run_id: str = typer.Option(None, "--run-id", help="Bind run_id"),
) -> None:
    from gps_agents.idempotency.decision import decide_upsert_source
    from gps_agents.gramps.models import Source as GSource
    from gps_agents.projections.sqlite_projection import SQLiteProjection
    from gps_agents.gramps.client import GrampsClient
    import json as _json

    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)

    cfg = get_config()
    proj = SQLiteProjection(str(cfg["data_dir"] / "projection.db"))
    gc = GrampsClient(cfg["data_dir"])  # not connecting

    s = GSource(title=title)
    dec = decide_upsert_source(gc, proj, s)
    console.print(_json.dumps(dec.__dict__, indent=2))


@plan_app.command("place")
def plan_place(
    name: str = typer.Option("", "--name"),
    city: str = typer.Option(None, "--city"),
    state: str = typer.Option(None, "--state"),
    country: str = typer.Option(None, "--country"),
    run_id: str = typer.Option(None, "--run-id"),
) -> None:
    from gps_agents.idempotency.decision import decide_upsert_place
    from gps_agents.gramps.models import Place as GPlace
    from gps_agents.projections.sqlite_projection import SQLiteProjection
    from gps_agents.gramps.client import GrampsClient
    import json as _json

    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)

    cfg = get_config()
    proj = SQLiteProjection(str(cfg["data_dir"] / "projection.db"))
    gc = GrampsClient(cfg["data_dir"])  # not connecting

    pl = GPlace(name=name, city=city, state=state, country=country)
    dec = decide_upsert_place(gc, proj, pl)
    console.print(_json.dumps(dec.__dict__, indent=2))


@plan_app.command("citation")
def plan_citation(
    source_id: str = typer.Option(..., "--source-id"),
    page: str = typer.Option(None, "--page"),
    year: int = typer.Option(None, "--year"),
    run_id: str = typer.Option(None, "--run-id"),
) -> None:
    from gps_agents.idempotency.decision import decide_upsert_citation
    from gps_agents.gramps.models import Citation as GCitation, GrampsDate
    from gps_agents.projections.sqlite_projection import SQLiteProjection
    from gps_agents.gramps.client import GrampsClient
    import json as _json

    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)

    cfg = get_config()
    proj = SQLiteProjection(str(cfg["data_dir"] / "projection.db"))
    gc = GrampsClient(cfg["data_dir"])  # not connecting

    cit = GCitation(source_id=source_id, page=page, date=GrampsDate(year=year) if year else None)
    dec = decide_upsert_citation(gc, proj, cit)
    console.print(_json.dumps(dec.__dict__, indent=2))


@plan_app.command("relationship")
def plan_relationship(
    kind: str = typer.Option(..., "--kind"),
    a: str = typer.Option(..., "--a"),
    b: str = typer.Option(..., "--b"),
    context: str = typer.Option(None, "--context"),
    run_id: str = typer.Option(None, "--run-id"),
) -> None:
    from gps_agents.idempotency.decision import decide_upsert_relationship
    from gps_agents.projections.sqlite_projection import SQLiteProjection
    from gps_agents.gramps.client import GrampsClient
    import json as _json

    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)

    cfg = get_config()
    proj = SQLiteProjection(str(cfg["data_dir"] / "projection.db"))
    gc = GrampsClient(cfg["data_dir"])  # not connecting

    dec = decide_upsert_relationship(gc, proj, kind, a, b, context)
    console.print(_json.dumps(dec.__dict__, indent=2))


@plan_app.command("batch")
def plan_batch(
    input: Path = typer.Option(..., "--input", help="JSON list of entities"),  # noqa: B008
    run_id: str = typer.Option(None, "--run-id"),
) -> None:
    """Batch planner: input is a list like:
    [
      {"entity":"person","given":"John","surname":"Doe"},
      {"entity":"event","type":"birth","year":1850}
    ]
    """
    import json as _json
    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)
    data = _json.loads(Path(input).read_text())

    from gps_agents.projections.sqlite_projection import SQLiteProjection
    from gps_agents.gramps.client import GrampsClient
    from gps_agents.idempotency.decision import (
        decide_upsert_person, decide_upsert_event, decide_upsert_source,
        decide_upsert_place, decide_upsert_citation, decide_upsert_relationship,
    )
    from gps_agents.gramps.models import (
        Person as GPerson, Name as GName, Event as GEvent, EventType as GEventType,
        GrampsDate, Source as GSource, Place as GPlace, Citation as GCitation,
    )

    cfg = get_config()
    proj = SQLiteProjection(str(cfg["data_dir"] / "projection.db"))
    gc = GrampsClient(cfg["data_dir"])  # not connecting

    decisions = []
    for item in data:
        et = item.get("entity")
        if et == "person":
            p = GPerson(names=[GName(given=item.get("given",""), surname=item.get("surname",""))])
            decisions.append(decide_upsert_person(gc, proj, p).__dict__)
        elif et == "event":
            ev = GEvent(event_type=GEventType(item.get("type","other")), date=GrampsDate(year=item.get("year")))
            decisions.append(decide_upsert_event(gc, proj, ev).__dict__)
        elif et == "source":
            s = GSource(title=item.get("title",""))
            decisions.append(decide_upsert_source(gc, proj, s).__dict__)
        elif et == "place":
            pl = GPlace(name=item.get("name",""), city=item.get("city"), state=item.get("state"), country=item.get("country"))
            decisions.append(decide_upsert_place(gc, proj, pl).__dict__)
        elif et == "citation":
            cit = GCitation(source_id=item.get("source_id",""), page=item.get("page"), date=GrampsDate(year=item.get("year")))
            decisions.append(decide_upsert_citation(gc, proj, cit).__dict__)
        elif et == "relationship":
            decisions.append(decide_upsert_relationship(gc, proj, item.get("kind",""), item.get("a",""), item.get("b",""), item.get("context")).__dict__)
    console.print(_json.dumps(decisions, indent=2))


@backfill_app.command("idempotency")
def backfill_idempotency(
    gramps_db: Path = typer.Argument(..., help="Path to Gramps sqlite.db/grampsdb.db"),  # noqa: B008
    run_id: str = typer.Option(None, "--run-id", help="Bind run_id to structured logs"),
) -> None:
    """Compute and persist fingerprints for existing Gramps records.

    Populates fingerprint_index and external_ids (gramps_handle only) for
    person/event/source/citation/place. Safe to re-run.
    """
    from gps_agents.gramps.client import GrampsClient
    from gps_agents.projections.sqlite_projection import SQLiteProjection
    from gps_agents.idempotency.fingerprint import (
        fingerprint_person, fingerprint_event, fingerprint_source,
        fingerprint_citation, fingerprint_place,
    )
    from gps_agents.gramps.models import Person as GPerson

    gc = GrampsClient(str(gramps_db))
    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)
    gc.connect(str(gramps_db))

    # Use projection in default data dir for simplicity
    proj = SQLiteProjection(str(get_config()["data_dir"] / "projection.db"))

    with gc.session():
        conn = gc._conn  # noqa: SLF001
        tables = [
            ("person", fingerprint_person),
            ("event", fingerprint_event),
            ("source", fingerprint_source),
            ("citation", fingerprint_citation),
            ("place", fingerprint_place),
        ]
        for table, fp_fn in tables:
            try:
                rows = conn.execute(f"SELECT handle, blob_data FROM {table}").fetchall()
            except Exception:
                continue
            count = 0
            for row in rows:
                handle = row["handle"]
                data = gc._deserialize_blob(row["blob_data"])  # noqa: SLF001
                # Minimal adapters to models used by fingerprint_* functions
                if table == "person":
                    person = gc._person_from_gramps(handle, data)
                    fp = fp_fn(person)
                elif table == "event":
                    from gps_agents.gramps.models import Event as GEvent
                    ev = GEvent.model_validate({**data}) if isinstance(data, dict) else GEvent()
                    fp = fp_fn(ev)
                elif table == "source":
                    from gps_agents.gramps.models import Source as GSource
                    s = GSource.model_validate({**data}) if isinstance(data, dict) else GSource()
                    fp = fp_fn(s)
                elif table == "citation":
                    from gps_agents.gramps.models import Citation as GCitation
                    c = GCitation.model_validate({**data}) if isinstance(data, dict) else GCitation()
                    fp = fp_fn(c)
                else:  # place
                    from gps_agents.gramps.models import Place as GPlace
                    pl = GPlace.model_validate({**data}) if isinstance(data, dict) else GPlace()
                    fp = fp_fn(pl)
                proj.ensure_fingerprint_row(table, fp.value)
                claimed = proj.claim_fingerprint_handle(fp.value, handle)
                if claimed == 0:
                    # someone else claimed; ok
                    pass
                else:
                    proj.set_external_ids(fp.value, gramps_handle=handle)
                count += 1
            console.print(f"[green]{table}: backfilled {count} rows[/green]")


@app.command()
def db_health(
    db_path: Path = typer.Option(None, "--db", help="Path to projection.db"),  # noqa: B008
    vacuum: bool = typer.Option(False, "--vacuum", help="VACUUM the database"),
    analyze: bool = typer.Option(False, "--analyze", help="ANALYZE the database"),
) -> None:
    """Show SQLite projection health and optionally VACUUM/ANALYZE."""
    cfg = get_config()
    proj_path = db_path or (cfg["data_dir"] / "projection.db")
    from gps_agents.projections.sqlite_projection import SQLiteProjection
    import sqlite3

    projection = SQLiteProjection(str(proj_path))
    with projection._get_conn() as conn:  # noqa: SLF001
        # PRAGMAs
        pragmas = {
            "foreign_keys": conn.execute("PRAGMA foreign_keys").fetchone()[0],
            "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
            "busy_timeout": conn.execute("PRAGMA busy_timeout").fetchone()[0],
            "page_count": conn.execute("PRAGMA page_count").fetchone()[0],
            "freelist_count": conn.execute("PRAGMA freelist_count").fetchone()[0],
        }
        # Counts
        tables = [
            "facts", "fact_sources", "persons", "external_ids", "fingerprint_index", "wikidata_statement_cache",
        ]
        counts = {}
        for t in tables:
            try:
                counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[t] = "N/A"
        # Maintenance
        if vacuum:
            conn.execute("VACUUM")
        if analyze:
            conn.execute("ANALYZE")

    table = Table(title=f"DB Health: {proj_path}")
    table.add_column("Metric")
    table.add_column("Value")
    for k, v in pragmas.items():
        table.add_row(k, str(v))
    for k, v in counts.items():
        table.add_row(k, str(v))
    console.print(table)


@app.command()
def stats() -> None:
    """Show statistics about the research database."""
    config = get_config()

    from gps_agents.projections.sqlite_projection import SQLiteProjection
    from gps_agents.sk.plugins.memory import MemoryPlugin

    projection = SQLiteProjection(str(config["data_dir"] / "projection.db"))
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

    # Memory stats
    memory = MemoryPlugin(str(config["data_dir"] / "chroma"))
    memory_stats = json.loads(memory.get_memory_stats())

    if memory_stats.get("available"):
        mem_table = Table(title="Semantic Memory Statistics")
        mem_table.add_column("Collection")
        mem_table.add_column("Count")

        for collection, count in memory_stats.get("collections", {}).items():
            mem_table.add_row(collection, str(count))

        console.print(mem_table)


@app.command()
def search(
    term: str = typer.Argument(..., help="Search term"),
    semantic: bool = typer.Option(False, "--semantic", "-s", help="Use semantic search"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results"),
) -> None:
    """Search fact statements."""
    config = get_config()

    if semantic:
        # Use ChromaDB semantic search
        from gps_agents.sk.plugins.memory import MemoryPlugin

        memory = MemoryPlugin(str(config["data_dir"] / "chroma"))
        results_json = memory.search_similar_facts(term, limit)
        results = json.loads(results_json)

        if not results:
            console.print(f"[yellow]No facts found matching '{term}'[/yellow]")
            return

        table = Table(title=f"Semantic Search Results for '{term}'")
        table.add_column("Statement")
        table.add_column("Similarity")

        for result in results:
            distance = result.get("distance", 0)
            similarity = f"{(1 - distance) * 100:.1f}%" if distance else "N/A"
            table.add_row(
                result.get("statement", "")[:60] + "...",
                similarity,
            )

        console.print(table)

    else:
        # Use SQLite text search
        from gps_agents.projections.sqlite_projection import SQLiteProjection

        projection = SQLiteProjection(str(config["data_dir"] / "projection.db"))
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


@app.command()
def memory_stats() -> None:
    """Show semantic memory statistics."""
    config = get_config()

    from gps_agents.sk.plugins.memory import MemoryPlugin

    memory = MemoryPlugin(str(config["data_dir"] / "chroma"))
    stats = json.loads(memory.get_memory_stats())

    if not stats.get("available"):
        console.print("[yellow]ChromaDB not available. Install with: pip install chromadb[/yellow]")
        return

    table = Table(title="Semantic Memory (ChromaDB)")
    table.add_column("Collection")
    table.add_column("Documents")

    for collection, count in stats.get("collections", {}).items():
        table.add_row(collection, str(count))

    console.print(table)
    console.print(f"[dim]Persist directory: {stats.get('persist_directory')}[/dim]")


def _display_chat_results(result: dict, verbose: bool) -> None:
    """Display research chat results."""
    chat_history = result.get("chat_history", [])

    if not chat_history:
        console.print("[yellow]No results from research session[/yellow]")
        return

    # Show final messages
    console.print("\n[bold]Research Summary:[/bold]")

    # Find synthesis or conclusion
    for msg in reversed(chat_history):
        content = msg.get("content", "")
        name = msg.get("name", "unknown")

        if "synthesis" in name.lower() or "conclusion" in content.lower() or "proof" in content.lower():
            console.print(Panel(content[:1000], title=f"[bold]{name}[/bold]"))
            break

    if verbose:
        console.print("\n[bold]Full Conversation:[/bold]")
        for msg in chat_history:
            name = msg.get("name", "unknown")
            content = msg.get("content", "")[:300]
            console.print(f"\n[bold]{name}:[/bold] {content}...")

    # Cost summary
    if result.get("cost"):
        console.print(f"\n[dim]Total cost: ${result['cost']:.4f}[/dim]")


def _save_results(result: dict, output: Path) -> None:
    """Save results to file."""
    output_data = {
        "query": result.get("query"),
        "chat_history": result.get("chat_history", []),
        "summary": result.get("summary"),
        "cost": result.get("cost"),
    }

    with open(output, "w") as f:
        json.dump(output_data, f, indent=2, default=str)


if __name__ == "__main__":
    app()
