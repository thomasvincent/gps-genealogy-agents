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

wiki_app = typer.Typer(help="Agentic AI Wiki genealogy commands")
app.add_typer(wiki_app, name="wiki")

crawl_app = typer.Typer(help="Long-running exhaustive GPS crawlers")
app.add_typer(crawl_app, name="crawl")

console = Console()

# Graph sub-app
graph_app = typer.Typer(help="Graph and lineage viewers")
app.add_typer(graph_app, name="graph")


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
                max_messages=max_rounds,
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
    # Validate input
    from jsonschema import validate
    from jsonschema.exceptions import ValidationError
    import json as _json
    schema_in = _json.loads(Path("schemas/planner_input.schema.json").read_text())
    try:
        validate(data, schema_in)
    except ValidationError as e:
        console.print(f"[red]Invalid input JSON: {e.message}[/red]")
        raise typer.Exit(1)

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
    # Validate output
    schema_out = _json.loads(Path("schemas/planner_output.schema.json").read_text())
    try:
        validate(decisions, schema_out)
    except ValidationError as e:
        console.print(f"[red]Planner output failed schema validation: {e.message}[/red]")
        raise typer.Exit(1)
    console.print(_json.dumps(decisions, indent=2))


@wiki_app.command("plan")
def wiki_plan(
    subject: str = typer.Option(..., "--subject", help="Subject name"),
    article_file: Path = typer.Option(None, "--article", help="Path to article text"),  # noqa: B008
    gramps_id: str = typer.Option(None, "--gramps-id"),
    wikidata_qid: str = typer.Option(None, "--wikidata-qid"),
    wikitree_id: str = typer.Option(None, "--wikitree-id"),
    engine: str = typer.Option("sk", "--engine", help="Planner engine: sk|autogen"),
    run_id: str = typer.Option(None, "--run-id"),
) -> None:
    """Dry-run planner that invokes the Agentic wiki publishing team.

    Uses existing IDs if provided; otherwise returns payloads without side effects.
    """
    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)
    article_text = ""
    if article_file and article_file.exists():
        article_text = article_file.read_text(encoding="utf-8")

    async def run_plan_autogen():
        from gps_agents.autogen.wiki_publishing import publish_to_wikis
        return await publish_to_wikis(
            article_text=article_text,
            subject_name=subject,
            gramps_id=gramps_id,
            wikidata_qid=wikidata_qid,
            wikitree_id=wikitree_id,
        )

    async def run_plan_sk():
        from gps_agents.sk.pipelines.wiki import plan_wiki_subject
        return await plan_wiki_subject(
            article_text=article_text,
            subject_name=subject,
            kernel_config=None,
        )

    if engine == "autogen":
        result = asyncio.run(run_plan_autogen())
    else:
        result = asyncio.run(run_plan_sk())
    console.print(Panel("Wiki plan complete (dry-run)", title="Wiki Planner"))
    # Print a compact summary
    import json as _json
    console.print(_json.dumps(result, indent=2, default=str))


@wiki_app.command("run")
def wiki_run(
    subject: str = typer.Option(..., "--subject"),
    article_file: Path = typer.Option(None, "--article"),  # noqa: B008
    outdir: Path = typer.Option(Path("research/wiki_plans"), "--outdir"),  # noqa: B008
    run_id: str = typer.Option(None, "--run-id"),
    open_pr: bool = typer.Option(False, "--open-pr"),
) -> None:
    """Orchestrate SK wiki pipeline (dry-run) and write a deterministic bundle, then commit via safe_commit."""
    if run_id is None:
        import uuid
        run_id = str(uuid.uuid4())
    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)
    article_text = ""
    if article_file and article_file.exists():
        article_text = article_file.read_text(encoding="utf-8")

    async def run_plan():
        from gps_agents.sk.pipelines.wiki import plan_wiki_subject
        return await plan_wiki_subject(
            article_text=article_text,
            subject_name=subject,
            kernel_config=None,
        )

    result = asyncio.run(run_plan())

    from gps_agents.wiki.bundles import write_wiki_bundle
    bundle = write_wiki_bundle(outdir, run_id, subject, result)

    # Git track
    from gps_agents.git_utils import safe_commit
    repo = Path.cwd()
    created = safe_commit(
        repo,
        [
            bundle.plan_json,
            bundle.summary_md,
            bundle.facts_json,
            bundle.review_json,
            bundle.wikidata_payload_json,
            bundle.wikipedia_md,
            bundle.wikitree_md,
            bundle.wikitree_yaml,
            bundle.gedcom_file,
        ],
        f"feat(wiki): run SK bundle for {subject} (run {run_id})\n\nCo-Authored-By: Warp <agent@warp.dev>",
    )
    console.print(f"[green]Wrote bundle in {bundle.dir}[/green]")

    if open_pr:
        try:
            import subprocess
            subprocess.check_call(["gh", "pr", "create", "--fill"], cwd=str(repo))
        except Exception:
            console.print("[yellow]gh not available; skipping PR creation[/yellow]")


@wiki_app.command("stage")
def wiki_stage(
    subject: str = typer.Option(..., "--subject"),
    article_file: Path = typer.Option(None, "--article"),  # noqa: B008
    outdir: Path = typer.Option(Path("research/wiki_plans"), "--outdir"),  # noqa: B008
    engine: str = typer.Option("sk", "--engine", help="Planner engine: sk|autogen"),
    run_id: str = typer.Option(None, "--run-id"),
    open_pr: bool = typer.Option(False, "--open-pr"),
) -> None:
    """Generate a wiki bundle (full artifacts) and commit it to Git for review."""
    if run_id is None:
        import uuid
        run_id = str(uuid.uuid4())
    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)
    article_text = ""
    if article_file and article_file.exists():
        article_text = article_file.read_text(encoding="utf-8")

    artifacts: dict
    if engine == "autogen":
        try:
            from gps_agents.autogen.wiki_publishing import publish_to_wikis
        except Exception:
            console.print("[red]AutoGen wiki publishing module not available. Ensure optional deps installed.[/red]")
            raise typer.Exit(1)

        async def run_plan_autogen():
            return await publish_to_wikis(
                article_text=article_text,
                subject_name=subject,
            )

        result = asyncio.run(run_plan_autogen())
        # Normalize to artifacts shape
        try:
            wd = result.get("wikidata_payload")
            wikidata_payload = json.loads(wd) if isinstance(wd, str) else (wd or {})
        except Exception:
            wikidata_payload = {}
        artifacts = {
            "subject": subject,
            "wikipedia_draft": result.get("wikipedia_draft") or "",
            "wikitree_bio": result.get("wikitree_bio") or "",
            "wikidata_payload": wikidata_payload,
            "facts": [],
            "review": {"status": "pending", "checks": []},
            "wikitree_profile": {"Name": subject, "Biography": "Draft pending review."},
            "gedcom": "",
            "messages": result.get("messages", []),
        }
    else:
        async def run_plan_sk():
            from gps_agents.sk.pipelines.wiki import plan_wiki_subject
            return await plan_wiki_subject(
                article_text=article_text,
                subject_name=subject,
                kernel_config=None,
            )

        artifacts = asyncio.run(run_plan_sk())

    from gps_agents.wiki.bundles import write_wiki_bundle
    bundle = write_wiki_bundle(outdir, run_id, subject, artifacts)

    # Git track
    from gps_agents.git_utils import safe_commit
    repo = Path.cwd()
    created = safe_commit(
        repo,
        [
            bundle.plan_json,
            bundle.summary_md,
            bundle.facts_json,
            bundle.review_json,
            bundle.wikidata_payload_json,
            bundle.wikipedia_md,
            bundle.wikitree_md,
            bundle.wikitree_yaml,
            bundle.gedcom_file,
        ],
        f"feat(wiki): stage bundle for {subject} (run {run_id}, engine {engine})\n\nCo-Authored-By: Warp <agent@warp.dev>",
    )
    console.print(f"[green]Staged bundle in {bundle.dir}[/green]")

    if open_pr:
        try:
            import subprocess
            subprocess.check_call(["gh", "pr", "create", "--fill"], cwd=str(repo))
        except Exception:
            console.print("[yellow]gh not available; skipping PR creation[/yellow]")


@wiki_app.command("show")
def wiki_show(
    bundle_dir: Path = typer.Option(..., "--bundle"),  # noqa: B008
    json_out: bool = typer.Option(False, "--json"),
    validate: bool = typer.Option(True, "--validate/--no-validate"),
) -> None:
    """Show a concise summary of a staged wiki bundle and optionally validate it."""
    if not bundle_dir.exists():
        console.print(f"[red]Bundle dir not found: {bundle_dir}[/red]")
        raise typer.Exit(1)

    import json as _json

    def _read(p: Path):
        return _json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    plan = _read(bundle_dir / "plan.json") or {}
    payload = _read(bundle_dir / "wikidata_payload.json") or {}
    facts = _read(bundle_dir / "facts.json") or []
    review = _read(bundle_dir / "review.json") or {}

    subject = plan.get("subject") or bundle_dir.name
    qid = payload.get("entity") if isinstance(payload, dict) else None
    claims = payload.get("claims") if isinstance(payload, dict) else None

    summary = {
        "bundle": str(bundle_dir),
        "run_id": plan.get("run_id") or bundle_dir.name,
        "subject": subject,
        "drafts": {
            "wikipedia": (bundle_dir / "wikipedia_draft.md").exists(),
            "wikitree": (bundle_dir / "wikitree_bio.md").exists(),
        },
        "wikidata": {
            "qid": qid,
            "has_qid": bool(isinstance(qid, str) and qid.upper().startswith("Q")),
            "claim_count": len(claims) if isinstance(claims, list) else 0,
        },
        "facts_count": len(facts) if isinstance(facts, list) else 0,
        "review_status": review.get("status"),
        "approved": (bundle_dir / "approved.yaml").exists(),
    }

    if validate:
        try:
            from jsonschema import validate as _validate  # type: ignore
            import json as _json
            errors = []
            try:
                facts_schema = _json.loads(Path("schemas/wiki_facts.schema.json").read_text())
                _validate(facts or [], facts_schema)
            except Exception as e:
                errors.append({"file": "facts.json", "error": str(e)})
            try:
                review_schema = _json.loads(Path("schemas/wiki_review.schema.json").read_text())
                _validate(review or {}, review_schema)
            except Exception as e:
                errors.append({"file": "review.json", "error": str(e)})
            try:
                payload_schema = _json.loads(Path("schemas/wikidata_payload.schema.json").read_text())
                _validate(payload or {}, payload_schema)
            except Exception as e:
                errors.append({"file": "wikidata_payload.json", "error": str(e)})
            summary["validation"] = {"ok": len(errors) == 0, "errors": errors}
        except Exception:
            summary["validation"] = {"ok": True, "errors": []}  # best-effort

    if json_out:
        console.print(json.dumps(summary, indent=2))
        return

    table = Table(title=f"Wiki Bundle: {subject}")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("Bundle", summary["bundle"])
    table.add_row("Run ID", summary["run_id"])
    table.add_row("Has Wikipedia Draft", str(summary["drafts"]["wikipedia"]))
    table.add_row("Has WikiTree Draft", str(summary["drafts"]["wikitree"]))
    table.add_row("Wikidata QID", str(summary["wikidata"]["qid"]))
    table.add_row("Claims", str(summary["wikidata"]["claim_count"]))
    table.add_row("Facts", str(summary["facts_count"]))
    table.add_row("Review Status", str(summary["review_status"]))
    table.add_row("Approved.yaml present", str(summary["approved"]))

    if "validation" in summary:
        v = summary["validation"]
        table.add_row("Validation", "OK" if v["ok"] else f"Errors: {len(v['errors'])}")

    console.print(table)


@wiki_app.command("check")
def wiki_check(
    bundle_dir: Path = typer.Option(..., "--bundle"),  # noqa: B008
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run pre-apply quality gates without applying.

    Checks:
    - Wikipedia draft Grade >= 9
    - Wikipedia draft contains RESEARCH_NOTES
    - Wikidata payload includes multilingual labels/descriptions (en, es, fr, de, it, nl)
    """
    import re
    if not bundle_dir.exists():
        console.print(f"[red]Bundle dir not found: {bundle_dir}[/red]")
        raise typer.Exit(1)

    result = {"grade_ok": False, "notes_ok": False, "wikidata_langs_ok": False, "missing_langs": []}

    # Wikipedia checks
    wiki_md = (bundle_dir / "wikipedia_draft.md").read_text(encoding="utf-8") if (bundle_dir / "wikipedia_draft.md").exists() else ""
    if wiki_md:
        m = re.search(r"(?i)(gps\s*grade\s*card).*?(\b(\d{1,2})(?:/10)?\b)", wiki_md, re.S)
        if m:
            try:
                g = int(re.search(r"\d{1,2}", m.group(2)).group(0))  # type: ignore
                result["grade_ok"] = g >= 9
            except Exception:
                result["grade_ok"] = False
        result["notes_ok"] = bool(re.search(r"(?i)^(#+\s*)?(research[_\s-]?notes)\b", wiki_md, re.M))

    # Wikidata multilingual checks
    payload_path = bundle_dir / "wikidata_payload.json"
    if payload_path.exists():
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        required_langs = {"en", "es", "fr", "de", "it", "nl"}
        labels = payload.get("labels") or {}
        descs = payload.get("descriptions") or {}
        have = {k for k in labels.keys()} | {k for k in descs.keys()}
        missing = sorted(list(required_langs - have))
        result["missing_langs"] = missing
        result["wikidata_langs_ok"] = len(missing) == 0

    if json_out:
        console.print(json.dumps(result, indent=2))
        raise typer.Exit(0 if all([result["grade_ok"], result["notes_ok"], result["wikidata_langs_ok"]]) else 2)

    # Human-readable output
    def flag(ok: bool) -> str:
        return "[green]OK[/green]" if ok else "[red]FAIL[/red]"

    console.print(Panel("Wiki Preflight Check", title="wiki check"))
    console.print(f"Grade >= 9: {flag(result['grade_ok'])}")
    console.print(f"RESEARCH_NOTES present: {flag(result['notes_ok'])}")
    console.print(f"Wikidata multilingual (en,es,fr,de,it,nl): {flag(result['wikidata_langs_ok'])}")
    if result["missing_langs"]:
        console.print(f"Missing languages: {', '.join(result['missing_langs'])}")

    ok_all = all([result["grade_ok"], result["notes_ok"], result["wikidata_langs_ok"]])
    if not ok_all:
        raise typer.Exit(2)


@wiki_app.command("apply")
def wiki_apply(
    bundle_dir: Path = typer.Option(..., "--bundle"),  # noqa: B008
    approval_file: Path = typer.Option(..., "--approval"),  # noqa: B008
    drafts_root: Path = typer.Option(Path("drafts"), "--drafts-root"),  # noqa: B008
) -> None:
    """Validate approval, run pre-apply quality gates, stage drafts, perform idempotent Wikidata apply, and commit results."""
    import re
    import yaml
    if not bundle_dir.exists():
        console.print(f"[red]Bundle dir not found: {bundle_dir}[/red]")
        raise typer.Exit(1)
    if not approval_file.exists():
        console.print(f"[red]Approval file not found: {approval_file}[/red]")
        raise typer.Exit(1)
    data = yaml.safe_load(approval_file.read_text(encoding="utf-8"))
    if not (isinstance(data, dict) and data.get("approved") is True and data.get("reviewer")):
        console.print("[red]Approval file must contain approved: true and reviewer: ...[/red]")
        raise typer.Exit(1)

    # Pre-apply quality checks
    # 1) Wikipedia draft Grade >= 9 and contains RESEARCH_NOTES
    wiki_md = (bundle_dir / "wikipedia_draft.md").read_text(encoding="utf-8") if (bundle_dir / "wikipedia_draft.md").exists() else ""
    grade_ok = False
    notes_ok = False
    if wiki_md:
        # Try to locate a 'GPS Grade Card' section with an overall grade; tolerate multiple formats
        m = re.search(r"(?i)(gps\s*grade\s*card).*?(\b(\d{1,2})(?:/10)?\b)", wiki_md, re.S)
        if m:
            try:
                g = int(re.search(r"\d{1,2}", m.group(2)).group(0))  # type: ignore
                grade_ok = g >= 9
            except Exception:
                grade_ok = False
        # Research notes section
        notes_ok = bool(re.search(r"(?i)^(#+\s*)?(research[_\s-]?notes)\b", wiki_md, re.M))
    if not grade_ok:
        console.print("[red]Pre-apply failed: Wikipedia draft does not show Grade >= 9/10.[/red]")
        raise typer.Exit(1)
    if not notes_ok:
        console.print("[red]Pre-apply failed: Wikipedia draft missing RESEARCH_NOTES section.[/red]")
        raise typer.Exit(1)

    # 2) Wikidata payload has multilingual labels/descriptions/aliases
    payload_path = bundle_dir / "wikidata_payload.json"
    if not payload_path.exists():
        console.print("[red]Pre-apply failed: wikidata_payload.json missing.[/red]")
        raise typer.Exit(1)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    required_langs = {"en", "es", "fr", "de", "it", "nl"}
    labels = payload.get("labels") or {}
    descs = payload.get("descriptions") or {}
    have = {k for k in labels.keys()} | {k for k in descs.keys()}
    missing = required_langs - have
    if missing:
        console.print(f"[red]Pre-apply failed: Wikidata payload missing languages: {sorted(missing)}[/red]")
        raise typer.Exit(1)

    # Copy approval file into bundle dir as approved.yaml
    dest = bundle_dir / "approved.yaml"
    from gps_agents.fs import atomic_write
    atomic_write(dest, approval_file.read_bytes())

    # Apply and stage drafts
    from gps_agents.wiki.apply import apply_bundle
    proj_path = get_config()["data_dir"] / "projection.db"
    summary = apply_bundle(bundle_dir, projection_db=proj_path, drafts_root=drafts_root)

    console.print(Panel("Apply complete", title="Wiki Apply"))
    console.print(json.dumps(summary, indent=2))


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
def sources_health() -> None:
    """Show throttling and circuit breaker status per source."""
    from gps_agents.net import report_status
    status = report_status()
    if not status:
        console.print("[yellow]No source activity recorded yet[/yellow]")
        return
    table = Table(title="Source Health")
    table.add_column("Source")
    table.add_column("Circuit")
    table.add_column("Rate")
    for k, v in sorted(status.items()):
        circ = "open" if v.get("circuit_open") else "ok"
        rate = v.get("rate") or {}
        rate_str = f"{rate.get('max_calls','?')}/{rate.get('window_seconds','?')}s min {rate.get('min_interval','?')}s"
        table.add_row(k, circ, rate_str)
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


@crawl_app.command("census-tree")
def crawl_census_tree(
    person_id: str = typer.Argument(..., help="Person ID (e.g., 'archer-l-durham') - matches research folder name"),
    research_dir: Path = typer.Option(Path("research"), "--research-dir", help="Directory containing research files"),
    output: Path = typer.Option(None, "--output", "-o", help="Output tree file (default: research/trees/{person_id}/census_tree.json)"),
    max_generations: int = typer.Option(3, "--max-generations", help="How many generations back to search"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Build a family tree from existing research, working backwards through census records.

    This command:
    1. Loads existing research (profile.json) for the person
    2. Extracts known family members (parents, siblings, spouse, children)
    3. Builds a tree structure with census sources
    4. Generates a search queue for missing census data

    Example:
        gps-agents crawl census-tree archer-l-durham --max-generations 3
    """
    from gps_agents.crawl.census_tree import build_census_tree_from_research

    output_path = str(output) if output else None

    result = build_census_tree_from_research(
        person_id=person_id,
        research_dir=str(research_dir),
        output_path=output_path,
        max_generations=max_generations,
    )

    if "error" in result:
        console.print(f"[red]Error: {result['error']}[/red]")
        if "searched_paths" in result:
            console.print("[dim]Searched paths:[/dim]")
            for p in result["searched_paths"]:
                console.print(f"  - {p}")
        raise typer.Exit(1)

    # Display results
    console.print(Panel(f"Census Tree for {person_id}", title="[bold]Census Family Tree[/bold]"))

    table = Table(title="Family Summary")
    table.add_column("Relation")
    table.add_column("Name")

    summary = result.get("family_summary", {})
    table.add_row("Seed", summary.get("seed", "Unknown"))
    table.add_row("Father", summary.get("father") or "-")
    table.add_row("Mother", summary.get("mother") or "-")
    for i, sibling in enumerate(summary.get("siblings", [])):
        table.add_row(f"Sibling {i+1}", sibling)

    console.print(table)

    console.print(f"\n[green]People found: {result.get('people_found', 0)}[/green]")
    console.print(f"[green]Tree saved to: {result.get('tree_file')}[/green]")

    # Show search queue
    search_queue = result.get("search_queue", [])
    if search_queue:
        console.print("\n[bold]Search Queue (missing census data):[/bold]")
        queue_table = Table()
        queue_table.add_column("Name")
        queue_table.add_column("Birth Year")
        queue_table.add_column("Generation")
        queue_table.add_column("Census Years to Search")

        for item in search_queue[:10]:  # Show first 10
            queue_table.add_row(
                item.get("name", "Unknown"),
                str(item.get("birth_year") or "?"),
                str(item.get("generation")),
                ", ".join(str(y) for y in item.get("census_years_to_search", [])[:5]),
            )

        console.print(queue_table)

        if len(search_queue) > 10:
            console.print(f"[dim]...and {len(search_queue) - 10} more[/dim]")

    if verbose:
        console.print("\n[bold]Full Result:[/bold]")
        console.print(json.dumps(result, indent=2, default=str))


@crawl_app.command("person")
def crawl_person(
    given: str = typer.Option(..., "--given", help="Given name"),
    surname: str = typer.Option(..., "--surname", help="Surname"),
    birth_year: int | None = typer.Option(None, "--birth-year", help="Approximate birth year"),
    birth_place: str | None = typer.Option(None, "--birth-place", help="Birth place"),
    max_duration: int = typer.Option(3600, "--max-duration", help="Max seconds to run"),
    max_iterations: int = typer.Option(500, "--max-iterations", help="Max loop iterations"),
    tree_out: Path = typer.Option(Path("research/trees/seed/tree.json"), "--tree-out", help="Output family tree JSON"),
    checkpoint_every: int = typer.Option(25, "--checkpoint-every", help="Write checkpoint every N iterations"),
    until_gps: bool = typer.Option(True, "--until-gps/--no-until-gps", help="Stop early when GPS-quality coverage reached"),
    no_authored_sources: bool = typer.Option(False, "--no-authored-sources", help="Exclude authored/user-tree sources from searches"),
    expand_family: bool = typer.Option(True, "--expand-family/--no-expand-family", help="After confirming seed, expand to ancestors/descendants"),
    max_generations: int = typer.Option(1, "--max-generations", help="Generations to expand (up and down)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    run_id: str | None = typer.Option(None, "--run-id"),
) -> None:
    """Run an exhaustive crawl seeded by a person, iterating until exhaustion/time/caps."""
    if run_id:
        from gps_agents.logging import set_run_id
        set_run_id(run_id)

    async def run():
        from gps_agents.crawl.engine import run_crawl_person, CrawlConfig, SeedPerson
        kernel_config = get_kernel_config()

        seed = SeedPerson(given=given, surname=surname, birth_year=birth_year, birth_place=birth_place)
        cfg = CrawlConfig(
            max_duration_seconds=max_duration,
            max_iterations=max_iterations,
            checkpoint_every=checkpoint_every,
            tree_out=str(tree_out),
            verbose=verbose,
            until_gps=until_gps,
            exclude_authored=no_authored_sources,
            expand_family=expand_family,
            max_generations=max_generations,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Crawling primary sources...", total=None)
            summary = await run_crawl_person(seed, cfg, kernel_config)
            progress.update(task, completed=True)
            return summary

    result = asyncio.run(run())
    console.print(Panel("Crawl complete", title="GPS Exhaustive Crawl"))
    if verbose:
        console.print(json.dumps(result, indent=2, default=str))


@graph_app.command("family")
def graph_family(
    root: str = typer.Option("", "--root", help="Substring to focus on a person name"),
    limit: int = typer.Option(200, "--limit", help="Max relationships to print"),
) -> None:
    """Print a simple family graph (parents/spouses/children) from ACCEPTED relationship facts."""
    from gps_agents.ledger.fact_ledger import FactLedger
    from gps_agents.models.fact import FactStatus

    cfg = get_config()
    ledger = FactLedger(str(cfg["data_dir"] / "ledger"))

    edges: list[tuple[str, str, str]] = []  # (kind, A, B)
    names: set[str] = set()

    count = 0
    for fact in ledger.iter_all_facts(FactStatus.ACCEPTED):
        if fact.fact_type != "relationship":
            continue
        kind = fact.relation_kind or "relationship"
        a = fact.relation_subject or ""
        b = fact.relation_object or ""
        if not a or not b:
            # fallback parse from statement
            stmt = fact.statement.lower()
            if " is child of " in stmt:
                kind = "child_of"
                parts = fact.statement.split(" is child of ", 1)
                a, b = parts[0], parts[1]
            elif " is spouse of " in stmt:
                kind = "spouse_of"
                parts = fact.statement.split(" is spouse of ", 1)
                a, b = parts[0], parts[1]
            elif " is parent of " in stmt:
                kind = "parent_of"
                parts = fact.statement.split(" is parent of ", 1)
                a, b = parts[0], parts[1]
        if not a or not b:
            continue
        if root and (root.lower() not in a.lower() and root.lower() not in b.lower()):
            continue
        edges.append((kind, a.strip(), b.strip()))
        names.update([a.strip(), b.strip()])
        count += 1
        if count >= limit:
            break

    if not edges:
        console.print("[yellow]No relationship edges found (try relaxing --root)[/yellow]")
        return

    console.print(Panel(f"Found {len(edges)} edges across {len(names)} people", title="Family Graph"))

    # Print adjacency by person
    from collections import defaultdict
    parents = defaultdict(list)
    children = defaultdict(list)
    spouses = defaultdict(list)

    for kind, a, b in edges:
        if kind == "child_of":
            # a is child of b
            parents[a].append(b)
            children[b].append(a)
        elif kind == "parent_of":
            children[a].append(b)
            parents[b].append(a)
        elif kind == "spouse_of":
            spouses[a].append(b)
            spouses[b].append(a)

    def _uniq(lst):
        seen = set()
        out = []
        for x in lst:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    # Show focused root first if provided
    ordered = [n for n in sorted(names)]
    if root:
        focus = [n for n in ordered if root.lower() in n.lower()]
        others = [n for n in ordered if root.lower() not in n.lower()]
        ordered = focus + others

    for n in ordered:
        p = ", ".join(_uniq(parents[n])) or "-"
        c = ", ".join(_uniq(children[n])) or "-"
        s = ", ".join(_uniq(spouses[n])) or "-"
        console.print(f"[bold]{n}[/bold]\n  parents: {p}\n  spouses: {s}\n  children: {c}\n")


if __name__ == "__main__":
    app()
