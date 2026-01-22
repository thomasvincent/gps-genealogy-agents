from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, Tuple, List, DefaultDict
from collections import defaultdict

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.models.fact import Fact, FactStatus


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


def export_gedcom(ledger_dir: Path, out_file: Path, root_filter: str = "") -> Path:
    """Export ACCEPTED facts and relationships to a minimal GEDCOM 5.5 file.

    - Individuals created from person_id keys and from relation subjects/objects
    - Families created from parent_of/child_of/spouse_of facts
    - Events: BIRT, DEAT, BURI attached to individuals when detected in statements
    """
    ledger = FactLedger(str(ledger_dir))

    # Build individuals and families in memory
    indi_ids: Dict[str, str] = {}  # display name -> @Ixx@
    indi_names: Dict[str, str] = {}  # indi_id -> NAME
    fam_ids: Dict[Tuple[str, str], str] = {}  # (HUSB,WIFE sorted) -> @Fxx@

    lines = []
    lines.append("0 HEAD")
    lines.append("1 SOUR gps-genealogy-agents")
    lines.append(f"1 DATE {datetime.now(UTC).strftime('%d %b %Y').upper()}")
    lines.append("1 GEDC")
    lines.append("2 VERS 5.5")
    lines.append("2 FORM LINEAGE-LINKED")
    lines.append("1 CHAR UTF-8")

    def _ensure_indi(display_name: str) -> str:
        if display_name not in indi_ids:
            iid = f"@I{len(indi_ids)+1}@"
            indi_ids[display_name] = iid
            indi_names[iid] = display_name
        return indi_ids[display_name]

    def _emit_event(indi_id: str, tag: str, fact: Fact) -> None:
        # Parse date/place best-effort from statement or extracted fields
        stmt = fact.statement
        date = None
        place = None
        # Simple date extraction if statement like "Birth on 12 Jan 1900" or "Death on 1900"
        parts = stmt.split(" on ", 1)
        if len(parts) == 2:
            date = parts[1].strip()
        if fact.sources and fact.sources[0].record_type:
            # Use event place if present in extracted fields is not accessible here; fallback none
            pass
        lines.append(f"0 {indi_id}")
        lines.append(f"1 {tag}")
        if date:
            lines.append(f"2 DATE {date}")
        if place:
            lines.append(f"2 PLAC {place}")

    # Pass 1: create individuals from person_ids and relation subjects/objects
    accepted = list(ledger.iter_all_facts(FactStatus.ACCEPTED))
    for fact in accepted:
        if fact.fact_type == "relationship":
            a = (fact.relation_subject or "").strip()
            b = (fact.relation_object or "").strip()
            if a:
                _ensure_indi(a)
            if b:
                _ensure_indi(b)
        else:
            if fact.person_id:
                nm = _name_from_person_key(fact.person_id)
                _ensure_indi(nm)

    # Emit INDI records with NAME
    for display_name, iid in indi_ids.items():
        lines.append(f"0 {iid} INDI")
        lines.append(f"1 NAME {display_name}")

    # Pass 2: create families and link spouses/children
    for fact in accepted:
        if fact.fact_type != "relationship":
            continue
        kind = (fact.relation_kind or "").lower()
        a = (fact.relation_subject or "").strip()
        b = (fact.relation_object or "").strip()
        if not a or not b:
            continue
        ia = _ensure_indi(a)
        ib = _ensure_indi(b)
        if kind == "spouse_of":
            key = tuple(sorted([ia, ib]))
            if key not in fam_ids:
                fam_ids[key] = f"@F{len(fam_ids)+1}@"
        elif kind in ("parent_of", "child_of"):
            # find or create family between parents if possible; otherwise create a generic family with unknown spouse
            # For simplicity, attach child to a synthetic family with the parent as HUSB (if male inference unavailable) and leave spouse blank
            # In practice, combining multiple facts will merge children under one family later
            key = tuple(sorted([ia, ib])) if kind == "spouse_of" else (ia, ib)
            # We'll add child links in pass 3
            pass

    # Collect child links per family
    fam_children: DefaultDict[str, List[str]] = defaultdict(list)
    for fact in accepted:
        if fact.fact_type != "relationship":
            continue
        kind = (fact.relation_kind or "").lower()
        a = (fact.relation_subject or "").strip()
        b = (fact.relation_object or "").strip()
        if not a or not b:
            continue
        ia = _ensure_indi(a)
        ib = _ensure_indi(b)
        if kind == "spouse_of":
            key = tuple(sorted([ia, ib]))
            if key not in fam_ids:
                fam_ids[key] = f"@F{len(fam_ids)+1}@"
        elif kind in ("parent_of", "child_of"):
            # Use synthetic family per parent (single-parent fam)
            parent = ia if kind == "parent_of" else ib
            child = ib if kind == "parent_of" else ia
            fid = fam_ids.get(tuple(sorted([parent, parent])))
            if not fid:
                fid = f"@F{len(fam_ids)+1}@"
                fam_ids[tuple(sorted([parent, parent]))] = fid
            fam_children[fid].append(child)

    # Emit FAM records (spouses and single-parent families)
    for (ia, ib), fid in fam_ids.items():
        lines.append(f"0 {fid} FAM")
        # If ia==ib this is single-parent synthetic; place as HUSB by default
        if ia == ib:
            lines.append(f"1 HUSB {ia}")
        else:
            lines.append(f"1 HUSB {ia}")
            lines.append(f"1 WIFE {ib}")
        for c in fam_children.get(fid, []):
            lines.append(f"1 CHIL {c}")

    # Emit FAMS/FAMC pointers: rebuild INDI sections with pointers is out of scope for minimal exporter
    # (Advanced enhancement: build INDI map first then output.)
    for (ia, ib), fid in fam_ids.items():
        lines.append(f"0 {fid} FAM")
        lines.append(f"1 HUSB {ia}")
        lines.append(f"1 WIFE {ib}")

    # Pass 3: child links
    for fact in accepted:
        if fact.fact_type != "relationship":
            continue
        kind = (fact.relation_kind or "").lower()
        a = (fact.relation_subject or "").strip()
        b = (fact.relation_object or "").strip()
        if not a or not b:
            continue
        ia = _ensure_indi(a)
        ib = _ensure_indi(b)
        if kind == "parent_of":
            parent = ia
            child = ib
        elif kind == "child_of":
            parent = ib
            child = ia
        else:
            continue
        # Attach child to a family with this parent; if none, create a single-parent family
        fam_key = tuple(sorted([parent, parent]))  # synthetic key for single parent
        if fam_key not in fam_ids:
            fam_ids[fam_key] = f"@F{len(fam_ids)+1}@"
            lines.append(f"0 {fam_ids[fam_key]} FAM")
            lines.append(f"1 HUSB {parent}")
        lines.append(f"1 CHIL {child}")

    # Pass 4: events for individuals
    for fact in accepted:
        if not fact.person_id:
            continue
        iid = _ensure_indi(_name_from_person_key(fact.person_id))
        t = fact.fact_type.lower()
        if t == "birth":
            _emit_event(iid, "BIRT", fact)
        elif t == "death":
            _emit_event(iid, "DEAT", fact)
        elif t == "burial":
            _emit_event(iid, "BURI", fact)

    # Trailer
    lines.append("0 TRLR")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines), encoding="utf-8")
    return out_file
