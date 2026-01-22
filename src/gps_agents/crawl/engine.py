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
from gps_agents.sources.familysearch import FamilySearchSource
from gps_agents.sources.usgenweb import USGenWebSource
from gps_agents.crawl.census_tree import CensusTreeBuilder, build_census_tree_from_research

# New free sources
from gps_agents.sources.billiongraves import BillionGravesSource
from gps_agents.sources.freecen_uk import FreeCENSource
from gps_agents.sources.cyndislist import CyndisListSource, NorwayBMDSource, BelgiumBMDSource
from gps_agents.sources.jewishgen import JewishGenSource, YadVashemSource
from gps_agents.sources.legacy_obituaries import LegacyObituariesSource, NewspaperObituariesSource
from gps_agents.sources.afrigeneas import (
    AfricanAmericanGenealogySource,
    FreedmansBureauSource,
    SlaveSchedulesSource,
)
from gps_agents.sources.library_of_congress import (
    LibraryOfCongressSource,
    ChroniclingAmericaSource,
    NYPLSource,
    ImmigrationRecordsSource,
)
from gps_agents.sources.california_vitals import CaliforniaVitalsSource
from gps_agents.sources.free_census import FreeCensusSource


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
    max_generations: int = 3    # BFS depth up/down (increased from 1)
    # New options for census tree expansion
    person_id: Optional[str] = None  # ID for loading existing research (e.g., "archer-l-durham")
    research_dir: str = "research"  # Directory containing existing research profiles
    use_existing_profile: bool = True  # Load family members from existing profile.json
    require_gps_approval: bool = False  # If False, expand family without LLM approval gate
    use_census_tree_builder: bool = True  # Use CensusTreeBuilder to generate search queue


async def run_crawl_person(seed: SeedPerson, cfg: CrawlConfig, kernel_config: Any | None = None) -> dict[str, Any]:
    """Minimal exhaustive crawl loop seeded by a person.

    Phase 1: search open sources (AccessGenealogy, WikiTree) repeatedly with
    widening query parameters and persist checkpoints.
    """
    start = time.time()
    iters = 0

    # Router with open sources only for Phase 1
    router = SearchRouter(RouterConfig(parallel=True, max_results_per_source=50))
    access_gen = AccessGenealogySource()
    usgenweb = USGenWebSource()
    router.register_source(access_gen)
    router.register_source(usgenweb)
    router.register_source(WikiTreeSource())
    router.register_source(Nara1950Source())
    router.register_source(Nara1940Source())
    router.register_source(FindAGraveSource())
    router.register_source(FreeBMDSource())

    # Add FamilySearch if configured (requires FAMILYSEARCH_ACCESS_TOKEN env var)
    fs_source = FamilySearchSource()
    if fs_source.is_configured():
        router.register_source(fs_source)
        if cfg.verbose:
            print("FamilySearch source enabled")

    # Cemetery and burial sources
    router.register_source(BillionGravesSource())

    # Vital records sources
    router.register_source(CaliforniaVitalsSource())

    # Free census sources (1940, 1950 fully indexed, others browsable)
    router.register_source(FreeCensusSource())

    # UK census (FreeCEN volunteer transcriptions)
    router.register_source(FreeCENSource())

    # Resource directories
    router.register_source(CyndisListSource())

    # Obituary sources
    router.register_source(LegacyObituariesSource())
    router.register_source(NewspaperObituariesSource())

    # Jewish genealogy
    router.register_source(JewishGenSource())
    router.register_source(YadVashemSource())

    # African American genealogy
    router.register_source(AfricanAmericanGenealogySource())
    router.register_source(FreedmansBureauSource())
    router.register_source(SlaveSchedulesSource())

    # Library and archive sources
    router.register_source(LibraryOfCongressSource())
    router.register_source(ChroniclingAmericaSource())
    router.register_source(NYPLSource())

    # Immigration records
    router.register_source(ImmigrationRecordsSource())

    if cfg.verbose:
        print("Census sources enabled: AccessGenealogy, USGenWeb, FreeCensus, FreeCEN")
        print("Vital records: California Death/Birth Index")
        print("Cemetery sources: FindAGrave, BillionGraves")
        print("Obituaries: Legacy.com, Chronicling America")
        print("Special collections: JewishGen, Afrigeneas, Freedmen's Bureau")
        print("Archives: Library of Congress, NYPL")

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

    # Load existing profile and seed family members into frontier
    if cfg.use_existing_profile and cfg.person_id:
        try:
            tree_builder = CensusTreeBuilder(cfg.research_dir)
            profile = tree_builder.load_existing_research(cfg.person_id)
            if profile:
                if cfg.verbose:
                    print(f"Loaded existing profile for {cfg.person_id}")
                # Extract family members
                family = tree_builder.extract_family_from_profile(profile)
                # Add parents (generation 1)
                for parent in family.get("parents", []):
                    if parent.given_name or parent.surname:
                        parent_seed = SeedPerson(
                            given=parent.given_name,
                            surname=parent.surname,
                            birth_year=parent.birth_year,
                            birth_place=parent.birth_place,
                        )
                        frontier.append((parent_seed, 1))
                        if cfg.verbose:
                            print(f"  Added parent to frontier: {parent.full_name}")
                # Add siblings (generation 0)
                for sibling in family.get("siblings", []):
                    if sibling.given_name or sibling.surname:
                        sib_seed = SeedPerson(
                            given=sibling.given_name,
                            surname=sibling.surname,
                            birth_year=sibling.birth_year,
                            birth_place=sibling.birth_place,
                        )
                        frontier.append((sib_seed, 0))
                        if cfg.verbose:
                            print(f"  Added sibling to frontier: {sibling.full_name}")
        except Exception as e:
            if cfg.verbose:
                print(f"Warning: Could not load existing profile: {e}")

    # Use CensusTreeBuilder to generate search queue for census expansion
    if cfg.use_census_tree_builder and cfg.person_id:
        try:
            tree_result = build_census_tree_from_research(
                cfg.person_id,
                research_dir=cfg.research_dir,
                max_generations=cfg.max_generations,
            )
            search_queue = tree_result.get("search_queue", [])
            if cfg.verbose:
                print(f"CensusTreeBuilder generated {len(search_queue)} search targets")
            for item in search_queue:
                name_parts = item.get("name", "").split()
                if name_parts:
                    queue_seed = SeedPerson(
                        given=name_parts[0] if name_parts else "",
                        surname=name_parts[-1] if len(name_parts) > 1 else "",
                        birth_year=item.get("birth_year"),
                        birth_place=item.get("birth_place"),
                    )
                    gen = item.get("generation", 1)
                    frontier.append((queue_seed, gen))
                    if cfg.verbose:
                        census_years = item.get("census_years_to_search", [])
                        print(f"  Added {item['name']} (gen {gen}) - census years: {census_years}")
        except Exception as e:
            if cfg.verbose:
                print(f"Warning: CensusTreeBuilder error: {e}")

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

        # Census-specific searches for household extraction
        # Extract state and county from birth_place
        state = None
        county = None
        if cur.birth_place:
            place_parts = cur.birth_place.split(",")
            if len(place_parts) >= 2:
                state = place_parts[-1].strip()
                city = place_parts[0].strip().lower()
                # Map known cities to their counties
                city_to_county = {
                    "pasadena": "Los Angeles",
                    "los angeles": "Los Angeles",
                    "glendale": "Los Angeles",
                    "burbank": "Los Angeles",
                    "long beach": "Los Angeles",
                    "san francisco": "San Francisco",
                    "oakland": "Alameda",
                    "san diego": "San Diego",
                    "sacramento": "Sacramento",
                    "san jose": "Santa Clara",
                    "fresno": "Fresno",
                }
                county = city_to_county.get(city, place_parts[0].strip())
            elif len(place_parts) == 1:
                state = place_parts[0].strip()

        if cfg.verbose and county:
            # Avoid "County County" duplication
            county_display = county if "county" in county.lower() else f"{county} County"
            print(f"  Census search targeting: {county_display}, {state}")

        # Search AccessGenealogy and USGenWeb for census transcriptions
        census_years = [1930, 1940]  # Most relevant for 1932 birth
        if cur.birth_year:
            # Add census years person would appear in (age 0+)
            census_years = [y for y in [1880, 1900, 1910, 1920, 1930, 1940, 1950] if y >= (cur.birth_year - 5)][:3]

        for year in census_years:
            try:
                ag_census = await access_gen.search_census(
                    surname=cur.surname,
                    given_name=cur.given,
                    state=state,
                    county=county,
                    year=year,
                )
                for rec in ag_census:
                    aggregated.append(rec.model_dump(mode="json"))
                    coverage["secondary_count"] += 1
                    coverage["sources"].add("accessgenealogy")
                    if cfg.verbose and rec.extracted_fields.get("household_members"):
                        members = rec.extracted_fields.get("household_members", [])
                        print(f"  AccessGenealogy {year} census: {len(members)} household members found")
            except Exception as e:
                if cfg.verbose:
                    print(f"  AccessGenealogy census {year} search error: {e}")

            try:
                ugw_census = await usgenweb.search_census(
                    surname=cur.surname,
                    given_name=cur.given,
                    state=state,
                    county=county,
                    year=year,
                )
                for rec in ugw_census:
                    aggregated.append(rec.model_dump(mode="json"))
                    coverage["secondary_count"] += 1
                    coverage["sources"].add("usgenweb")
                    if cfg.verbose and rec.extracted_fields.get("household_members"):
                        members = rec.extracted_fields.get("household_members", [])
                        print(f"  USGenWeb {year} census: {len(members)} household members found")
            except Exception as e:
                if cfg.verbose:
                    print(f"  USGenWeb census {year} search error: {e}")

        # Process all aggregated census records and extract household members for frontier
        if cfg.expand_family and gen < cfg.max_generations:
            for rec_dict in aggregated[-20:]:  # Check recent records
                if rec_dict.get("record_type") != "census":
                    continue
                extracted = rec_dict.get("extracted_fields", {})
                household_members = extracted.get("household_members", [])
                if not household_members:
                    continue

                # Extract persons from census household
                persons = _extract_persons_from_census_household(household_members, cur.surname)
                for given, surname, byear, rel in persons:
                    # Determine generation based on relationship
                    rel_lower = (rel or "").lower()
                    if rel_lower in ("father", "mother", "parent"):
                        new_gen = gen + 1  # Parents are one generation up
                    elif rel_lower in ("son", "daughter", "child"):
                        new_gen = gen  # Children are same or down
                    elif rel_lower in ("head", "self"):
                        continue  # Skip self
                    else:
                        new_gen = gen  # Siblings, spouses stay at same gen level

                    member_key = _person_key(given, surname, byear, None)
                    if member_key not in visited:
                        member_seed = SeedPerson(given=given, surname=surname, birth_year=byear)
                        frontier.append((member_seed, new_gen))
                        if cfg.verbose:
                            print(f"    Added census household member: {given} {surname} ({rel or 'unknown'}, gen {new_gen})")

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
                            # Expand family if GPS approved OR if approval not required
                            if decision == "ACCEPT" or not cfg.require_gps_approval:
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
            "sources": sorted(list(cov.get("sources", []))),
            "records": cov.get("count", 0),
            "primary": cov.get("primary_count", 0),
            "secondary": cov.get("secondary_count", 0),
            "authored": cov.get("authored_count", 0),
        },
        "records": records[:2000],
    }
    path.write_text(json.dumps(payload, indent=2))

    # Also emit GEDCOM and Mermaid alongside the tree.json
    try:
        from gps_agents.export.gedcom import export_gedcom
        from gps_agents.export.mermaid import export_mermaid
        export_gedcom(Path("data/ledger"), path.with_suffix(".ged"))
        export_mermaid(Path("data/ledger"), path.with_suffix(".mmd"))
    except Exception:
        pass


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
    - secondary: indexes/derivative abstracts (FreeBMD, AccessGenealogy, FindAGrave, USGenWeb)
    - authored: user trees/compiled narratives (WikiTree)
    """
    src = (rec.source or "").lower()
    rtype = (rec.record_type or "").lower()
    if src in {"nara1950", "nara1940"}:
        return "primary"
    if src in {"freebmd", "accessgenealogy", "findagrave", "usgenweb"}:
        return "secondary"
    if src in {"wikitree"}:
        return "authored"
    # Fallback by record type keywords
    if any(k in rtype for k in ["image", "original", "population schedule", "certificate"]):
        return "primary"
    if any(k in rtype for k in ["index", "transcript", "abstract", "burial", "census"]):
        return "secondary"
    return "secondary"


def _extract_persons_from_census_household(
    household_members: list[dict[str, str]],
    target_surname: str,
) -> list[tuple[str, str, int | None, str | None]]:
    """Extract (given, surname, birth_year, relationship) from census household data.

    Args:
        household_members: List of dicts with name, age, relationship, birthplace, etc.
        target_surname: The surname we're researching

    Returns:
        List of (given_name, surname, estimated_birth_year, relationship)
    """
    persons = []
    target_surname_lower = target_surname.lower()

    for member in household_members:
        name = member.get("name", "")
        if not name:
            continue

        # Parse name - could be "John Smith", "Smith, John", or just "John"
        name_parts = name.replace(",", " ").split()
        if len(name_parts) >= 2:
            # Assume first-last or last-first format
            if target_surname_lower in name.lower():
                # Surname matches - parse accordingly
                given = name_parts[0] if not name_parts[0].lower() == target_surname_lower else " ".join(name_parts[1:])
                surname = target_surname
            else:
                given = name_parts[0]
                surname = name_parts[-1]
        elif len(name_parts) == 1:
            given = name_parts[0]
            surname = target_surname
        else:
            continue

        # Estimate birth year from age if available
        birth_year = None
        age_str = member.get("age", "")
        if age_str and age_str.isdigit():
            age = int(age_str)
            # Census year would be needed for accurate calc - estimate ~1930
            birth_year = 1935 - age  # Rough estimate

        relationship = member.get("relationship", "")

        persons.append((given, surname, birth_year, relationship))

    return persons
