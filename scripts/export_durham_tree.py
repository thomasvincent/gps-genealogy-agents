#!/usr/bin/env python3
"""Export Archer Durham's family tree to GEDCOM format.

Based on research findings from FamilySearch and primary source validation.
"""

from datetime import datetime, UTC
from pathlib import Path


# Family tree data from research
FAMILY_TREE = {
    "archer_durham": {
        "name": "Archer Lyman Durham",
        "sex": "M",
        "birth_date": "9 JUN 1932",
        "birth_place": "Pasadena, Los Angeles, California, USA",
        "father": "barney_durham",
        "mother": "ruby_sorrell",
        "sources": ["FamilySearch Tree ID: G6WG-W8R (mother)", "US Census 1940"],
    },
    "barney_durham": {
        "name": "Barney M Durham",
        "sex": "M",
        "birth_date": "ABT 1895",
        "birth_place": "Georgia, USA",
        "father": None,
        "mother": None,
        "sources": ["FamilySearch Tree", "US Census 1940"],
    },
    "ruby_sorrell": {
        "name": "Ruby Zenobia Sorrell",
        "sex": "F",
        "birth_date": "ABT 1903",
        "birth_place": "Vinita, Cherokee, Oklahoma, USA",
        "father": "morris_sorrell",
        "mother": "ida_madden",
        "sources": [
            "FamilySearch Tree ID: G6WG-W8R",
            "NUMIDENT (Social Security) - parents: Maurice Sorrell, Ida Madden",
            "Five Civilized Tribes Enrollment Records hint",
        ],
    },
    "morris_sorrell": {
        "name": "Morris A Sorrell",
        "sex": "M",
        "birth_date": "28 MAY 1874",
        "birth_place": "Oklahoma, USA",
        "death_date": "4 JAN 1958",
        "death_place": "Riverside, California, USA",
        "father": "morris_sorrell_sr",
        "mother": "dicey_tinnon",
        "sources": [
            "FamilySearch Tree ID: G6J7-L61",
            "California Death Index - Morris A Sorrell",
            "Name variants: Maurice, Morris A.",
        ],
    },
    "ida_madden": {
        "name": "Ida Madden",
        "sex": "F",
        "birth_date": "ABT 1880",
        "birth_place": "Oklahoma, USA",
        "father": None,
        "mother": None,
        "sources": [
            "NUMIDENT record for Ruby Sorrell",
            "Name variants: Ida Manley",
        ],
    },
    "morris_sorrell_sr": {
        "name": "Morris Sorrell Sr",
        "sex": "M",
        "birth_date": "ABT 1850",
        "birth_place": "Oklahoma, USA",
        "father": None,
        "mother": None,
        "sources": ["FamilySearch Tree ID: GGZJ-JL1"],
    },
    "dicey_tinnon": {
        "name": "Dicey Tinnon",
        "sex": "F",
        "birth_date": "ABT 1854",
        "birth_place": "Oklahoma, USA",
        "death_date": "ABT 1895",
        "death_place": "Oklahoma, USA",
        "father": None,
        "mother": None,
        "sources": ["FamilySearch Tree"],
    },
}

# Marriages/Families
FAMILIES = [
    {
        "husband": "archer_durham",
        "wife": None,
        "children": [],
    },
    {
        "husband": "barney_durham",
        "wife": "ruby_sorrell",
        "children": ["archer_durham"],
        "marriage_date": "ABT 1930",
        "marriage_place": "California, USA",
    },
    {
        "husband": "morris_sorrell",
        "wife": "ida_madden",
        "children": ["ruby_sorrell"],
        "marriage_date": "ABT 1900",
        "marriage_place": "Oklahoma, USA",
    },
    {
        "husband": "morris_sorrell_sr",
        "wife": "dicey_tinnon",
        "children": ["morris_sorrell"],
        "marriage_date": "ABT 1870",
        "marriage_place": "Oklahoma, USA",
    },
]


def generate_gedcom() -> str:
    """Generate GEDCOM 5.5.1 format family tree."""
    lines = []

    # Header
    lines.append("0 HEAD")
    lines.append("1 SOUR gps-genealogy-agents")
    lines.append("2 VERS 1.0")
    lines.append("2 NAME GPS Genealogy Agents")
    lines.append(f"1 DATE {datetime.now(UTC).strftime('%d %b %Y').upper()}")
    lines.append("1 GEDC")
    lines.append("2 VERS 5.5.1")
    lines.append("2 FORM LINEAGE-LINKED")
    lines.append("1 CHAR UTF-8")
    lines.append("1 NOTE Archer Durham family tree - GPS-compliant research")

    # Create individual IDs
    indi_ids = {}
    for i, key in enumerate(FAMILY_TREE.keys(), 1):
        indi_ids[key] = f"@I{i}@"

    # Create family IDs
    fam_ids = {}
    for i, fam in enumerate(FAMILIES, 1):
        fam_ids[i-1] = f"@F{i}@"

    # Emit individuals
    for key, person in FAMILY_TREE.items():
        iid = indi_ids[key]
        lines.append(f"0 {iid} INDI")

        # Name
        name_parts = person["name"].split()
        if len(name_parts) >= 2:
            given = " ".join(name_parts[:-1])
            surname = name_parts[-1]
            lines.append(f"1 NAME {given} /{surname}/")
            lines.append(f"2 GIVN {given}")
            lines.append(f"2 SURN {surname}")
        else:
            lines.append(f"1 NAME {person['name']}")

        # Sex
        lines.append(f"1 SEX {person['sex']}")

        # Birth
        if person.get("birth_date"):
            lines.append("1 BIRT")
            lines.append(f"2 DATE {person['birth_date']}")
            if person.get("birth_place"):
                lines.append(f"2 PLAC {person['birth_place']}")

        # Death
        if person.get("death_date"):
            lines.append("1 DEAT")
            lines.append(f"2 DATE {person['death_date']}")
            if person.get("death_place"):
                lines.append(f"2 PLAC {person['death_place']}")

        # Sources as notes
        if person.get("sources"):
            for src in person["sources"]:
                lines.append(f"1 NOTE Source: {src}")

        # Family links (FAMC = family as child, FAMS = family as spouse)
        for i, fam in enumerate(FAMILIES):
            fid = fam_ids[i]
            # As child
            if key in fam.get("children", []):
                lines.append(f"1 FAMC {fid}")
            # As spouse
            if fam.get("husband") == key or fam.get("wife") == key:
                lines.append(f"1 FAMS {fid}")

    # Emit families
    for i, fam in enumerate(FAMILIES):
        fid = fam_ids[i]
        lines.append(f"0 {fid} FAM")

        if fam.get("husband"):
            lines.append(f"1 HUSB {indi_ids[fam['husband']]}")
        if fam.get("wife"):
            lines.append(f"1 WIFE {indi_ids[fam['wife']]}")

        # Marriage
        if fam.get("marriage_date"):
            lines.append("1 MARR")
            lines.append(f"2 DATE {fam['marriage_date']}")
            if fam.get("marriage_place"):
                lines.append(f"2 PLAC {fam['marriage_place']}")

        # Children
        for child_key in fam.get("children", []):
            lines.append(f"1 CHIL {indi_ids[child_key]}")

    # Trailer
    lines.append("0 TRLR")

    return "\n".join(lines)


def print_tree_summary():
    """Print a text summary of the family tree."""
    print("\n" + "=" * 70)
    print(" ARCHER DURHAM FAMILY TREE")
    print(" GPS-Compliant Research Results")
    print("=" * 70)

    print("\n DIRECT LINEAGE (4 Generations):")
    print("-" * 50)

    print("""
    Archer Lyman DURHAM (b. 9 Jun 1932, Pasadena, CA)
    │
    ├── Father: Barney M DURHAM (b. ~1895, Georgia)
    │   └── [Further research needed on Durham line]
    │
    └── Mother: Ruby Zenobia SORRELL (b. ~1903, Vinita, Cherokee, OK)
        │
        ├── Father: Morris A SORRELL (b. 28 May 1874, OK; d. 4 Jan 1958, Riverside, CA)
        │   │
        │   ├── Father: Morris SORRELL Sr. (b. ~1850, OK)
        │   │
        │   └── Mother: Dicey TINNON (b. ~1854, OK; d. ~1895, OK)
        │
        └── Mother: Ida MADDEN (b. ~1880, OK)
            └── [Name variant: Ida Manley]
    """)

    print("\n PRIMARY SOURCE VALIDATION STATUS:")
    print("-" * 50)
    print("  ✓ Ruby Sorrell: NUMIDENT confirms parents (Maurice Sorrell, Ida Madden)")
    print("  ✓ Morris Sorrell: California Death Index confirms dates")
    print("  ⚠ Cherokee Freedmen: Dawes Rolls search pending validation")
    print("  ⚠ Dicey Tinnon: Needs census record confirmation")
    print("  ⚠ Barney Durham: Georgia ancestry needs research")

    print("\n FAMILYSEARCH TREE IDs:")
    print("-" * 50)
    print("  Ruby Zenobia Sorrell: G6WG-W8R")
    print("  Morris Sorrell: G6J7-L61")
    print("  Morris Sorrell Sr: GGZJ-JL1")


def main():
    """Export family tree to GEDCOM and print summary."""
    print_tree_summary()

    # Generate GEDCOM
    gedcom_content = generate_gedcom()

    # Save to file
    output_dir = Path("data/gedcom")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"archer_durham_tree_{datetime.now().strftime('%Y%m%d')}.ged"
    output_file.write_text(gedcom_content, encoding="utf-8")

    print(f"\n GEDCOM file saved to: {output_file}")
    print(f" File size: {output_file.stat().st_size} bytes")
    print(f" Individuals: {len(FAMILY_TREE)}")
    print(f" Families: {len(FAMILIES)}")

    return output_file


if __name__ == "__main__":
    main()
