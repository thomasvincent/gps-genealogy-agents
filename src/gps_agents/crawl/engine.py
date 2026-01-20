from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from gps_agents.models.search import SearchQuery
from gps_agents.sources.router import SearchRouter, RouterConfig, Region
from gps_agents.sources.accessgenealogy import AccessGenealogySource
from gps_agents.sources.wikitree import WikiTreeSource
from gps_agents.sources.nara1950 import Nara1950Source
from gps_agents.sources.nara1940 import Nara1940Source
from gps_agents.sources.findagrave import FindAGraveSource
from gps_agents.sources.freebmd import FreeBMDSource


@dataclass
class SeedPerson:
    given: str
    surname: str
    birth_year: Optional[int] = None
    birth_place: Optional[str] = None


@dataclass
class CrawlConfig:
    max_duration_seconds: int = 3600
    max_iterations: int = 500
    checkpoint_every: int = 25
    tree_out: str = "research/trees/seed/tree.json"
    verbose: bool = False
    until_gps: bool = True  # stop early when GPS-quality coverage reached (primary+secondary, no authored-only)
    exclude_authored: bool = False  # exclude user-generated trees (e.g., WikiTree) from searches
    expand_family: bool = True  # after confirming a person, expand to relatives
    max_generations: int = 1    # BFS depth up/down


async def run_crawl_person(seed: SeedPerson, cfg: CrawlConfig, kernel_config: Any | None = None) -> dict[str, Any]:
    """Minimal exhaustive crawl loop seeded by a person.

    Phase 1: search open sources (AccessGenealogy, WikiTree) repeatedly with
    widening query parameters and persist checkpoints.
    """
    start = time.time()
    iters = 0

    # Router with open sources only for Phase 1
    router = SearchRouter(RouterConfig(parallel=True, max_results_per_source=50))
    router.register_source(AccessGenealogySource())
    router.register_source(WikiTreeSource())
    router.register_source(Nara1950Source())
    router.register_source(Nara1940Source())
    router.register_source(FindAGraveSource())
    router.register_source(FreeBMDSource())

    # Ensure output directory
    out_path = Path(cfg.tree_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Simple state
    aggregated: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {
        "sources": set(),
        "count": 0,
        "primary_count": 0,
        "secondary_count": 0,
        "authored_count": 0,
    }

    # Lazy import for extraction and ledger to keep deps light for other commands
    from gps_agents.extractors.accessgenealogy import fetch_parse_people_table
    from gps_agents.ledger.fact_ledger import FactLedger
    from gps_agents.models.fact import Fact, FactStatus
    from gps_agents.models.source import SourceCitation, EvidenceType
    from gps_agents.models.provenance import Provenance, ProvenanceSource

    ledger = FactLedger("data/ledger")

# BFS frontier of people to process
    from collections import deque
    PersonSeed = tuple[str, str | None, str | None, int]  # (name, birth_place, person_key, gen)

    def _person_key(given: str, surname: str, byear: Optional[int], bplace: Optional[str]) -> str:
        return f"{given} {surname}|{byear or ''}|{bplace or ''}"

    region = Region.USA if (seed.birth_place and "united" in seed.birth_place.lower() or True) else None  # default USA
    root_key = _person_key(seed.given, seed.surname, seed.birth_year, seed.birth_place)
    frontier: deque[tuple[SeedPerson, int]] = deque([(seed, 0)])
    visited: set[str] = set()
    accepted_counts: dict[str, int] = {}

    while frontier and iters < cfg.max_iterations and (time.time() - start) < cfg.max_duration_seconds:
        cur, gen = frontier.popleft()
        key = _person_key(cur.given, cur.surname, cur.birth_year, cur.birth_place)
        if key in visited:
            continue
        visited.add(key)
        iters += 1
        # Expand search window every 100 iters if needed (placeholder)
        query = SearchQuery(
            given_name=cur.given,
            surname=cur.surname,
            birth_year=cur.birth_year,
            birth_place=cur.birth_place,
            record_types=["census", "birth", "death", "marriage"],
            exclude_sources=["wikitree"] if cfg.exclude_authored else [],
        )

        unified = await router.search(query, region=region)

        # Aggregate and classify
        for rec in unified.results:
            aggregated.append(rec.model_dump(mode="json"))
            cat = _classify_record(rec)
            if cat == "primary":
                coverage["primary_count"] += 1
            elif cat == "secondary":
                coverage["secondary_count"] += 1
            elif cat == "authored":
                coverage["authored_count"] += 1
        for s in unified.sources_searched:
            coverage["sources"].add(s)
        coverage["count"] = len(aggregated)

        # Early stop condition on seed only (primary + secondary; no dependency on authored trees)
        if cur is seed and cfg.until_gps and coverage["primary_count"] >= 1 and coverage["secondary_count"] >= 1:
            # seed confirmed
            accepted_counts.setdefault(key, 0)

        # Extract structured people from AccessGenealogy tables and write proposed facts
        for rec in unified.results:
            rsrc = rec.source.lower()
            # AccessGenealogy: table rows -> roll/census listing facts
            if rsrc == "accessgenealogy" and rec.url and rec.extracted_fields.get("has_tabular_data") == "true":
                try:
                    people = await fetch_parse_people_table(rec.url)
                except Exception:
                    people = []
                for p in people[:50]:
                    if not p.name:
                        continue
                    stmt = f"{p.name} listed in roll with number {p.roll_number}" if p.roll_number else f"{p.name} listed in roll/census table"
                    citation = SourceCitation(
                        repository=rec.source,
                        record_id=rec.record_id,
                        url=rec.url,
                        evidence_type=EvidenceType.DIRECT,
                        record_type=rec.record_type,
                        original_text=None,
                    )
                    fact = Fact(
                        statement=stmt,
                        sources=[citation],
                        provenance=Provenance(
                            created_by=ProvenanceSource.WEB_SCRAPING,
                            discovery_method="table_parse",
                            raw_response=None,
                        ),
                        fact_type="roll_listing",
                        person_id=key,
                        confidence_score=0.6 if p.roll_number else 0.5,
                        status=FactStatus.PROPOSED,
                    )
                    ledger.append(fact)
                    try:
                        await _evaluate_and_promote_fact(fact, ledger, kernel_config)
                    except Exception:
                        pass
            # FreeBMD: index row -> index fact
            if rsrc == "freebmd" and rec.extracted_fields.get("index_row"):
                from gps_agents.extractors.freebmd import parse_index_row
                fields = parse_index_row(rec.extracted_fields.get("index_row") or "")
                event = fields.get("event") or "index"
                name = fields.get("name") or "Subject"
                year = fields.get("year") or ""
                quarter = fields.get("quarter") or ""
                district = fields.get("district") or ""
                vol = fields.get("volume") or ""
                page = fields.get("page") or ""
                parts = [f"{name}", f"{event} index"]
                if year:
                    parts.append(year)
                if quarter:
                    parts.append(quarter)
                if district:
                    parts.append(district)
                if vol or page:
                    parts.append(f"Vol {vol} Page {page}".strip())
                stmt = ", ".join([p for p in parts if p])
                citation = SourceCitation(
                    repository=rec.source,
                    record_id=rec.record_id or "",
                    url=rec.url or "",
                    evidence_type=EvidenceType.INDIRECT,
                    record_type=event,
                    original_text=rec.extracted_fields.get("index_row"),
                )
                fact = Fact(
                    statement=stmt,
                    sources=[citation],
                    provenance=Provenance(
                        created_by=ProvenanceSource.WEB_SCRAPING,
                        discovery_method="freebmd_index_row",
                        raw_response=None,
                    ),
                    fact_type=f"{event}_index",
                    person_id=key,
                    confidence_score=0.55,
                    status=FactStatus.PROPOSED,
                )
                ledger.append(fact)
                try:
                    await _evaluate_and_promote_fact(fact, ledger, kernel_config)
                except Exception:
                    pass
            # Find A Grave: memorial -> burial/death/birth facts
            if rsrc == "findagrave" and rec.url:
                from gps_agents.extractors.findagrave import fetch_parse_memorial
                try:
                    m = await fetch_parse_memorial(rec.url)
                except Exception:
                    m = {}
                # Burial fact
                if m.get("cemetery_name"):
                    stmt = f"Burial at {m.get('cemetery_name')} ({m.get('cemetery_location') or ''})".strip()
                    citation = SourceCitation(
                        repository=rec.source,
                        record_id=rec.record_id,
                        url=rec.url,
                        evidence_type=EvidenceType.INDIRECT,
                        record_type="burial",
                        original_text=None,
                    )
                    fact = Fact(
                        statement=stmt,
                        sources=[citation],
                        provenance=Provenance(
                            created_by=ProvenanceSource.WEB_SCRAPING,
                            discovery_method="findagrave_memorial",
                            raw_response=None,
                        ),
                        fact_type="burial",
                        person_id=key,
                        confidence_score=0.6,
                        status=FactStatus.PROPOSED,
                    )
                    ledger.append(fact)
                    try:
                        await _evaluate_and_promote_fact(fact, ledger, kernel_config)
                    except Exception:
                        pass
                # Death date fact
                if m.get("death_date"):
                    stmt = f"Death on {m.get('death_date')} (memorial)"
                    citation = SourceCitation(
                        repository=rec.source,
                        record_id=rec.record_id,
                        url=rec.url,
                        evidence_type=EvidenceType.INDIRECT,
                        record_type="death",
                        original_text=None,
                    )
                    fact = Fact(
                        statement=stmt,
                        sources=[citation],
                        provenance=Provenance(
                            created_by=ProvenanceSource.WEB_SCRAPING,
                            discovery_method="findagrave_memorial",
                            raw_response=None,
                        ),
                        fact_type="death",
                        person_id=key,
                        confidence_score=0.55,
                        status=FactStatus.PROPOSED,
                    )
                    ledger.append(fact)
                    try:
                        await _evaluate_and_promote_fact(fact, ledger, kernel_config)
                    except Exception:
                        pass
                # Birth date fact
                if m.get("birth_date"):
                    stmt = f"Birth on {m.get('birth_date')} (memorial)"
                    citation = SourceCitation(
                        repository=rec.source,
                        record_id=rec.record_id,
                        url=rec.url,
                        evidence_type=EvidenceType.INDIRECT,
                        record_type="birth",
                        original_text=None,
                    )
                    fact = Fact(
                        statement=stmt,
                        sources=[citation],
                        provenance=Provenance(
                            created_by=ProvenanceSource.WEB_SCRAPING,
                            discovery_method="findagrave_memorial",
                            raw_response=None,
                        ),
                        fact_type="birth",
                        person_id=key,
                        confidence_score=0.5,
                        status=FactStatus.PROPOSED,
                    )
                    ledger.append(fact)
                    try:
                        await _evaluate_and_promote_fact(fact, ledger, kernel_config)
                    except Exception:
                        pass

                # Queue relatives only when a relationship fact is ACCEPTED by GPS critics
                if cfg.expand_family and gen < cfg.max_generations and m.get("family_members"):
                    fam = m.get("family_members", {})

                    async def _relate_and_maybe_enqueue(names: list[str], relation: str) -> None:
                        for nm in names:
                            # Make a relationship statement based on relation type
                            subj = f"{cur.given} {cur.surname}".strip()
                            if not subj:
                                continue
                            if relation == "parent":
                                stmt = f"{subj} is child of {nm}"
                                rel_kind = "child_of"
                            elif relation == "spouse":
                                stmt = f"{subj} is spouse of {nm}"
                                rel_kind = "spouse_of"
                            else:  # child
                                stmt = f"{subj} is parent of {nm}"
                                rel_kind = "parent_of"
                            citation = SourceCitation(
                                repository=rec.source,
                                record_id=rec.record_id,
                                url=rec.url,
                                evidence_type=EvidenceType.INDIRECT,
                                record_type="relationship",
                                original_text=None,
                            )
                            rel_fact = Fact(
                                statement=stmt,
                                sources=[citation],
                                provenance=Provenance(
                                    created_by=ProvenanceSource.WEB_SCRAPING,
                                    discovery_method="findagrave_family_members",
                                    raw_response=None,
                                ),
                                fact_type="relationship",
                                relation_kind=rel_kind,
                                relation_subject=subj,
                                relation_object=nm,
                                person_id=key,
                                confidence_score=0.5,
                                status=FactStatus.PROPOSED,
                            )
                            ledger.append(rel_fact)
                            try:
                                decision = await _evaluate_and_promote_fact(rel_fact, ledger, kernel_config)
                            except Exception:
                                decision = "INCOMPLETE"
                            if decision == "ACCEPT":
                                # parse name and enqueue
                                parts = nm.split(", ") if "," in nm else nm.split()
                                if not parts:
                                    continue
                                if "," in nm:
                                    surname = parts[0]
                                    given = " ".join(parts[1:]).strip()
                                else:
                                    given = parts[0]
                                    surname = parts[-1] if len(parts) > 1 else ""
                                child = SeedPerson(given=given, surname=surname)
                                child_key = _person_key(given, surname, None, None)
                                if child_key not in visited:
                                    frontier.append((child, gen + 1))

                    await _relate_and_maybe_enqueue(fam.get("parents", []), "parent")
                    await _relate_and_maybe_enqueue(fam.get("spouses", []), "spouse")
                    await _relate_and_maybe_enqueue(fam.get("children", []), "child")
                        pass

        # Checkpoint
        if iters % cfg.checkpoint_every == 0:
            _write_tree_checkpoint(out_path, seed, aggregated, coverage)

        # Minimal backoff to respect sites
        await asyncio.sleep(0.5)

    # Final write
    _write_tree_checkpoint(out_path, seed, aggregated, coverage)
    return {
        "iterations": iters,
        "duration_sec": int(time.time() - start),
        "records": len(aggregated),
        "sources": sorted(list(coverage["sources"])),
        "coverage": {
            "primary": coverage.get("primary_count", 0),
            "secondary": coverage.get("secondary_count", 0),
            "authored": coverage.get("authored_count", 0),
        },
        "tree_file": str(out_path),
        "stopped_on_gps": bool(cfg.until_gps and coverage.get("primary_count", 0) >= 1 and coverage.get("secondary_count", 0) >= 1),
    }


def _write_tree_checkpoint(path: Path, seed: SeedPerson, records: list[dict[str, Any]], cov: dict[str, Any]) -> None:
    payload = {
        "seed": seed.__dict__,
        "coverage": {
            "sources": sorted(list(cov["sources"])),
            "records": cov.get("count", 0),
            "primary": cov.get("primary_count", 0),
            "secondary": cov.get("secondary_count", 0),


async def _evaluate_and_promote_fact(fact: Any, ledger: Any, kernel_config: Any | None) -> str:
    """Run GPS critics via autogen and promote fact status accordingly.

    Returns the final decision string: ACCEPT, REJECT, or INCOMPLETE.
    """
    if kernel_config is None:
        return "INCOMPLETE"
    try:
        from gps_agents.autogen.orchestration import evaluate_fact_gps
    except Exception:
        return "INCOMPLETE"

    # Serialize the fact for evaluation
    fact_json = fact.model_dump_json()
    result = await evaluate_fact_gps(fact_json, kernel_config)
    msgs = result.get("evaluation", [])
    text = "\n".join([m.get("content", "") for m in msgs])
    decision = "INCOMPLETE"
    if "ACCEPT" in text.upper():
        decision = "ACCEPT"
    elif "REJECT" in text.upper():
        decision = "REJECT"

    from gps_agents.models.fact import FactStatus, Annotation

    annotation = Annotation(author="gps_critics", content=text, annotation_type="evaluation")

    updated = fact.add_annotation(annotation)
    if decision == "ACCEPT":
        updated = updated.set_status(FactStatus.ACCEPTED)
    elif decision == "REJECT":
        updated = updated.set_status(FactStatus.REJECTED)
    else:
        updated = updated.set_status(FactStatus.INCOMPLETE)

    ledger.append(updated)
    return decision


def _classify_record(rec: Any) -> str:
    """Rudimentary classification into primary/secondary/authored.

    - primary: NARA 1940/1950 (original images), civil/church images when available
    - secondary: indexes/derivative abstracts (FreeBMD, AccessGenealogy, FindAGrave)
    - authored: user trees/compiled narratives (WikiTree)
    """
    src = (rec.source or "").lower()
    rtype = (rec.record_type or "").lower()
    if src in {"nara1950", "nara1940"}:
        return "primary"
    if src in {"freebmd", "accessgenealogy", "findagrave"}:
        return "secondary"
    if src in {"wikitree"}:
        return "authored"
    # Fallback by record type keywords
    if any(k in rtype for k in ["image", "original", "population schedule", "certificate"]):
        return "primary"
    if any(k in rtype for k in ["index", "transcript", "abstract", "burial", "census"]):
        return "secondary"
    return "secondary"
