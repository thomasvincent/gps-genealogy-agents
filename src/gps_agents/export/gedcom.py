from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from dataclasses import dataclass, field

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.models.fact import Fact, FactStatus


@dataclass
class GedcomEvent:
    tag: str
    date: str | None = None
    place: str | None = None


@dataclass
class GedcomIndividual:
    indi_id: str
    name: str
    events: list[GedcomEvent] = field(default_factory=list)
    fams_ids: set[str] = field(default_factory=set)  # Families as spouse (set for O(1) lookup)
    famc_ids: set[str] = field(default_factory=set)  # Families as child (set for O(1) lookup)


@dataclass
class GedcomFamily:
    fam_id: str
    husb_id: str | None = None
    wife_id: str | None = None
    child_ids: set[str] = field(default_factory=set)  # Set for O(1) lookup


def _name_from_person_key(person_key: str) -> str:
    # person_key looks like "Given Surname|YEAR|PLACE"; take left side
    left = person_key.split("|")[0].strip()
    if not left:
        return "Unknown /Unknown/"
    parts = left.split()
    if len(parts) == 1:
        given = parts[0]
        surname = "Unknown"
    else:
        given = " ".join(parts[:-1])
        surname = parts[-1]
    return f"{given} /{surname}/"


def _parse_event_from_fact(fact: Fact) -> tuple[str | None, str | None]:
    stmt = fact.statement
    date = None
    place = None
    # Simple date extraction if statement like "Birth on 12 Jan 1900"
    parts = stmt.split(" on ", 1)
    if len(parts) == 2:
        date = parts[1].strip()
    # Could extract place from fact.sources if available
    return date, place


def export_gedcom(ledger_dir: Path, out_file: Path, root_filter: str = "") -> Path:
    """Export ACCEPTED facts and relationships to a minimal GEDCOM 5.5 file.

    Args:
        ledger_dir: Path to the fact ledger directory
        out_file: Output file path for the GEDCOM file
        root_filter: Optional filter for root individual (not yet implemented)

    Returns:
        Path to the created GEDCOM file

    Note:
        - Individuals created from person_id keys and from relation subjects/objects
        - Families created from parent_of/child_of/spouse_of facts
        - Events: BIRT, DEAT, BURI attached to individuals when detected in statements
    """
    ledger = FactLedger(str(ledger_dir))

    # Build data structures in memory first
    individuals: dict[str, GedcomIndividual] = {}  # display_name -> GedcomIndividual
    families: dict[tuple[str, str], GedcomFamily] = {}  # (sorted spouse ids) -> GedcomFamily
    fam_id_to_family: dict[str, GedcomFamily] = {}  # fam_id -> GedcomFamily (reverse lookup)
    name_to_id: dict[str, str] = {}  # display_name -> indi_id
    id_to_indi: dict[str, GedcomIndividual] = {}  # indi_id -> GedcomIndividual (reverse lookup)

    def _ensure_indi(display_name: str) -> str:
        if display_name not in name_to_id:
            indi_id = f"@I{len(name_to_id) + 1}@"
            name_to_id[display_name] = indi_id
            indi = GedcomIndividual(indi_id=indi_id, name=display_name)
            individuals[display_name] = indi
            id_to_indi[indi_id] = indi  # Populate reverse lookup
        return name_to_id[display_name]

    def _ensure_family(spouse1_id: str, spouse2_id: str | None = None) -> str:
        # Create a consistent key (sorted for spouse pairs, single for single-parent)
        if spouse2_id and spouse1_id != spouse2_id:
            key = tuple(sorted([spouse1_id, spouse2_id]))
        else:
            key = (spouse1_id, spouse1_id)

        if key not in families:
            fam_id = f"@F{len(families) + 1}@"
            fam = GedcomFamily(fam_id=fam_id)
            families[key] = fam
            fam_id_to_family[fam_id] = fam  # Populate reverse lookup
            # Set spouses
            if spouse2_id and spouse1_id != spouse2_id:
                fam.husb_id = key[0]
                fam.wife_id = key[1]
            else:
                fam.husb_id = spouse1_id
        return families[key].fam_id

    # Single-pass processing: create individuals, families, and events in one iteration
    # Map fact types to GEDCOM tags for event processing
    EVENT_TAG_MAP = {"birth": "BIRT", "death": "DEAT", "burial": "BURI"}

    for fact in ledger.iter_all_facts(FactStatus.ACCEPTED):
        fact_type = (fact.fact_type or "").lower()

        if fact_type == "relationship":
            # Process relationship: create individuals and families
            a = (fact.relation_subject or "").strip()
            b = (fact.relation_object or "").strip()

            # Ensure both individuals exist
            if a:
                _ensure_indi(a)
            if b:
                _ensure_indi(b)

            # Create family relationships if both parties present
            if a and b:
                ia = name_to_id[a]
                ib = name_to_id[b]
                kind = (fact.relation_kind or "").lower()

                if kind == "spouse_of":
                    fam_id = _ensure_family(ia, ib)
                    # Add FAMS pointers to both spouses (O(1) set operations)
                    id_to_indi[ia].fams_ids.add(fam_id)
                    id_to_indi[ib].fams_ids.add(fam_id)

                elif kind == "parent_of":
                    # Parent is 'a', child is 'b' (O(1) set operations)
                    fam_id = _ensure_family(ia)
                    fam_id_to_family[fam_id].child_ids.add(ib)
                    id_to_indi[ib].famc_ids.add(fam_id)

                elif kind == "child_of":
                    # Child is 'a', parent is 'b' (O(1) set operations)
                    fam_id = _ensure_family(ib)
                    fam_id_to_family[fam_id].child_ids.add(ia)
                    id_to_indi[ia].famc_ids.add(fam_id)

        elif fact.person_id:
            # Process person fact: create individual and attach events
            nm = _name_from_person_key(fact.person_id)
            _ensure_indi(nm)

            # Check if this fact type maps to a GEDCOM event tag
            tag = EVENT_TAG_MAP.get(fact_type)
            if tag:
                date, place = _parse_event_from_fact(fact)
                individuals[nm].events.append(GedcomEvent(tag=tag, date=date, place=place))

    # Now emit the GEDCOM file
    lines: list[str] = []

    # Header
    lines.append("0 HEAD")
    lines.append("1 SOUR gps-genealogy-agents")
    lines.append(f"1 DATE {datetime.now(UTC).strftime('%d %b %Y').upper()}")
    lines.append("1 GEDC")
    lines.append("2 VERS 5.5")
    lines.append("2 FORM LINEAGE-LINKED")
    lines.append("1 CHAR UTF-8")

    # Emit INDI records
    for name, indi in individuals.items():
        lines.append(f"0 {indi.indi_id} INDI")
        lines.append(f"1 NAME {indi.name}")

        # Emit events nested under INDI
        for event in indi.events:
            lines.append(f"1 {event.tag}")
            if event.date:
                lines.append(f"2 DATE {event.date}")
            if event.place:
                lines.append(f"2 PLAC {event.place}")

        # Emit FAMS pointers (families where this person is a spouse)
        for fam_id in indi.fams_ids:
            lines.append(f"1 FAMS {fam_id}")

        # Emit FAMC pointers (families where this person is a child)
        for fam_id in indi.famc_ids:
            lines.append(f"1 FAMC {fam_id}")

    # Emit FAM records
    for key, fam in families.items():
        lines.append(f"0 {fam.fam_id} FAM")
        if fam.husb_id:
            lines.append(f"1 HUSB {fam.husb_id}")
        if fam.wife_id:
            lines.append(f"1 WIFE {fam.wife_id}")
        for child_id in fam.child_ids:
            lines.append(f"1 CHIL {child_id}")

    # Trailer
    lines.append("0 TRLR")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines), encoding="utf-8")
    return out_file
