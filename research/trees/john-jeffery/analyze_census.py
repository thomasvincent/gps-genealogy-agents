"""Analyze census data for John Jeffery research case.

This script processes census YAML files and performs GPS-compliant analysis:
- Birth year calculation from ages
- Geographic tracking
- Household reconstruction
- Consistency checking
- Spouse/children identification
"""

import yaml
from pathlib import Path
from datetime import datetime
from collections import Counter

def load_census_data(census_dir: Path) -> dict[int, dict]:
    """Load all census YAML files."""
    census_data = {}

    for year in [1841, 1851, 1861]:
        file_path = census_dir / f"census_{year}.yaml"
        if file_path.exists():
            with open(file_path) as f:
                data = yaml.safe_load(f)
                census_data[year] = data
        else:
            print(f"⚠️  Missing: {file_path}")

    return census_data


def calculate_birth_years(census_data: dict[int, dict]) -> dict:
    """Calculate birth year from each census age."""
    birth_years = {}

    for year, data in census_data.items():
        age_str = data.get("person", {}).get("age", "")

        if not age_str or age_str == "":
            continue

        try:
            age = int(age_str)

            # Handle 1841 rounding (ages rounded down to nearest 5)
            if year == 1841 and age >= 15:
                # Could be age to age+4
                birth_year_min = year - age - 4
                birth_year_max = year - age
                birth_years[year] = {
                    "age": age,
                    "birth_year_range": f"{birth_year_min}-{birth_year_max}",
                    "birth_year_best": year - age - 2,  # Midpoint
                }
            else:
                birth_years[year] = {
                    "age": age,
                    "birth_year": year - age,
                }
        except ValueError:
            print(f"⚠️  Invalid age in {year} census: '{age_str}'")

    return birth_years


def analyze_consistency(birth_years: dict) -> dict:
    """Check consistency of birth years across censuses."""
    calculated_years = []

    for year, data in birth_years.items():
        if "birth_year" in data:
            calculated_years.append(data["birth_year"])
        elif "birth_year_best" in data:
            calculated_years.append(data["birth_year_best"])

    if not calculated_years:
        return {"consistent": False, "reason": "No birth years calculated"}

    year_counter = Counter(calculated_years)
    most_common_year, count = year_counter.most_common(1)[0]

    # Check if all years are within ±2 (accounting for age reporting errors)
    min_year = min(calculated_years)
    max_year = max(calculated_years)
    range_span = max_year - min_year

    consistent = range_span <= 2

    return {
        "consistent": consistent,
        "birth_year_estimate": most_common_year,
        "range": f"{min_year}-{max_year}",
        "span": range_span,
        "all_calculated": calculated_years,
    }


def extract_household_members(census_data: dict[int, dict]) -> dict:
    """Extract household composition from each census."""
    households = {}

    for year, data in census_data.items():
        household = data.get("household", [])

        if not household:
            continue

        members = []
        for person in household:
            members.append({
                "name": person.get("name", ""),
                "age": person.get("age", ""),
                "relationship": person.get("relationship", ""),
                "birthplace": person.get("birthplace", ""),
            })

        households[year] = {
            "size": len(household),
            "members": members,
        }

    return households


def identify_spouse(households: dict) -> dict | None:
    """Identify spouse from household data."""
    spouse_candidates = {}

    for year, data in households.items():
        for member in data["members"]:
            rel = member["relationship"].lower()
            if rel in ["wife", "spouse"]:
                name = member["name"]
                spouse_candidates[name] = spouse_candidates.get(name, 0) + 1

    if not spouse_candidates:
        return None

    # Most common spouse name across censuses
    spouse_name = max(spouse_candidates, key=spouse_candidates.get)
    appearances = spouse_candidates[spouse_name]

    return {
        "name": spouse_name,
        "appearances": appearances,
        "confidence": "high" if appearances >= 2 else "medium",
    }


def identify_children(households: dict) -> list[dict]:
    """Identify children from household data."""
    children_by_name = {}

    for year, data in households.items():
        for member in data["members"]:
            rel = member["relationship"].lower()
            if rel in ["son", "daughter", "child"]:
                name = member["name"]
                age = member.get("age", "")

                if name not in children_by_name:
                    children_by_name[name] = {
                        "name": name,
                        "appearances": [],
                        "birth_year_estimates": [],
                    }

                children_by_name[name]["appearances"].append(year)

                # Calculate birth year
                if age and age != "":
                    try:
                        birth_year = year - int(age)
                        children_by_name[name]["birth_year_estimates"].append(birth_year)
                    except ValueError:
                        pass

    # Convert to list and calculate average birth years
    children = []
    for child_data in children_by_name.values():
        if child_data["birth_year_estimates"]:
            avg_birth = sum(child_data["birth_year_estimates"]) // len(child_data["birth_year_estimates"])
            child_data["birth_year"] = avg_birth
        children.append(child_data)

    return sorted(children, key=lambda x: x.get("birth_year", 9999))


def track_geography(census_data: dict[int, dict]) -> dict:
    """Track geographic locations across censuses."""
    locations = {}

    for year, data in census_data.items():
        address = data.get("address", {})
        birthplace = data.get("person", {}).get("birthplace", "")

        locations[year] = {
            "residence": {
                "street": address.get("street", ""),
                "parish": address.get("parish", ""),
                "county": address.get("county", ""),
            },
            "birthplace": birthplace,
        }

    # Determine if person moved
    parishes = [loc["residence"]["parish"] for loc in locations.values() if loc["residence"]["parish"]]
    counties = [loc["residence"]["county"] for loc in locations.values() if loc["residence"]["county"]]

    moved_parish = len(set(parishes)) > 1
    moved_county = len(set(counties)) > 1

    return {
        "locations": locations,
        "moved_parish": moved_parish,
        "moved_county": moved_county,
        "parishes": list(set(parishes)),
        "counties": list(set(counties)),
    }


def generate_report(census_dir: Path) -> None:
    """Generate comprehensive census analysis report."""
    print("=" * 80)
    print("CENSUS ANALYSIS REPORT: John Jeffery")
    print("=" * 80)
    print()

    # Load data
    census_data = load_census_data(census_dir)

    if not census_data:
        print("❌ No census data files found!")
        print(f"   Expected files in: {census_dir}")
        print("   - census_1841.yaml")
        print("   - census_1851.yaml")
        print("   - census_1861.yaml")
        return

    print(f"✓ Loaded {len(census_data)} census records")
    print()

    # Birth year analysis
    print("📅 BIRTH YEAR ANALYSIS")
    print("-" * 80)
    birth_years = calculate_birth_years(census_data)

    for year, data in birth_years.items():
        if "birth_year" in data:
            print(f"  {year}: Age {data['age']} → Born ~{data['birth_year']}")
        else:
            print(f"  {year}: Age {data['age']} → Born {data['birth_year_range']} (1841 rounding)")

    consistency = analyze_consistency(birth_years)
    print()
    print(f"  Consistency: {'✓ CONSISTENT' if consistency['consistent'] else '⚠️  INCONSISTENT'}")
    print(f"  Best estimate: {consistency.get('birth_year_estimate', 'N/A')}")
    print(f"  Range: {consistency.get('range', 'N/A')} (span: {consistency.get('span', 0)} years)")
    print()

    # Geography analysis
    print("🗺️  GEOGRAPHIC TRACKING")
    print("-" * 80)
    geo = track_geography(census_data)

    for year, loc in geo["locations"].items():
        res = loc["residence"]
        parish = res["parish"] or "Unknown"
        county = res["county"] or "Unknown"
        birthplace = loc["birthplace"] or "Unknown"
        print(f"  {year}: {parish}, {county}")
        print(f"        Birthplace: {birthplace}")

    print()
    print(f"  Movement: {'Yes, moved between parishes' if geo['moved_parish'] else 'No, stayed in same parish'}")
    print(f"  Counties: {', '.join(geo['counties']) if geo['counties'] else 'Unknown'}")
    print()

    # Household analysis
    print("👨‍👩‍👧‍👦 HOUSEHOLD COMPOSITION")
    print("-" * 80)
    households = extract_household_members(census_data)
    spouse = None
    children = []

    if households:
        for year, household in households.items():
            print(f"  {year} Census ({household['size']} members):")
            for member in household["members"]:
                print(f"    - {member['name']}, age {member['age']} ({member['relationship']})")
        print()

        # Spouse identification
        spouse = identify_spouse(households)
        if spouse:
            print(f"  Spouse: {spouse['name']} (appears {spouse['appearances']}x, confidence: {spouse['confidence']})")
        else:
            print(f"  Spouse: Not identified")

        # Children identification
        children = identify_children(households)
        if children:
            print(f"  Children ({len(children)}):")
            for child in children:
                birth_year = child.get("birth_year", "?")
                appearances = len(child["appearances"])
                print(f"    - {child['name']}, b. ~{birth_year} (appears {appearances}x)")
        else:
            print(f"  Children: None identified")
    else:
        print("  ⚠️  No household data available")

    print()

    # GPS Assessment
    print("📋 GPS ASSESSMENT")
    print("-" * 80)

    # Pillar 3: Analysis & Correlation
    print("  Pillar 3 (Analysis & Correlation):")
    if consistency.get("consistent"):
        print("    ✓ Birth year consistent across censuses")
    elif consistency.get("span"):
        print(f"    ⚠️  Birth year range spans {consistency['span']} years (investigate)")
    else:
        print("    ⚠️  No birth year data available (fill in census ages)")

    if spouse:
        print(f"    ✓ Spouse identified: {spouse['name']}")
    else:
        print("    ⚠️  Spouse not identified")

    if children:
        print(f"    ✓ Children identified: {len(children)}")
    else:
        print("    ⚠️  No children identified")

    print()
    print("  Next Steps:")
    print("    1. Compare birthplace across censuses for consistency")
    print("    2. Search for marriage record with spouse name")
    print("    3. Check if children appear in Michigan with subject")
    print("    4. Verify no census records after 1861 in England (emigration)")
    print("    5. Search Michigan records for spouse/children")
    print()
    print("=" * 80)


if __name__ == "__main__":
    census_dir = Path(__file__).parent
    generate_report(census_dir)
