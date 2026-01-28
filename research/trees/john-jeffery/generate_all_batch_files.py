#!/usr/bin/env python3
"""Generate all manual validation batch files for all tiers."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from rich.console import Console

console = Console()


async def main():
    """Generate batch files for all tiers."""
    validation_results_file = Path("ancestry_validation_results.json")
    extracted_data_file = Path("familysearch_extracted_data.json")

    # Load data
    with open(validation_results_file) as f:
        validation_results = json.load(f)

    extracted_data = {}
    if extracted_data_file.exists():
        with open(extracted_data_file) as f:
            extracted_data = json.load(f)

    already_validated = set(extracted_data.get("data", {}).keys())

    # Get all pending profiles
    pending = []
    for wt_id, profile in validation_results["validated_profiles"].items():
        if wt_id not in already_validated:
            pending.append({
                "wikitree_id": wt_id,
                "search_url": profile["familysearch_search_url"],
                "wikitree_data": profile["wikitree_data"]
            })

    # Define tiers
    tiers = {
        "tier1": {
            "name": "Generation 2 (Direct Parents)",
            "profiles": ["Jeffery-390", "Hickmott-289", "Jefferies-721",
                        "Hubbard-7253", "Jeffcoat-234", "Fardon-19"],
            "priority": "HIGH - Validate these first"
        },
        "tier2": {
            "name": "Generation 3 (Grandparents)",
            "profiles": ["Jeffery-1237", "Baldwin-8616", "Hickmott-283", "Avery-5760",
                        "Avery-5821", "Aynscombe-10", "Jefferies-887", "Thorold-88",
                        "Hubbard-7254", "Gardiner-4482", "Jefferies-881", "Kybird-2"],
            "priority": "MEDIUM - Good coverage expected"
        },
        "tier3": {
            "name": "GPS Compliance Profiles",
            "profiles": ["Hickmott-290", "Hickmott-299", "Russell-7272", "Fardon-20",
                        "Hubbard-8642", "Clayton-6804"],
            "priority": "MEDIUM - Reach 75% threshold"
        },
        "tier4": {
            "name": "Optional Completion",
            "profiles": ["Unknown-238808", "Avery-9713"],
            "priority": "LOW - Challenging records"
        }
    }

    console.print("\n[bold cyan]Generating Batch Files for All Tiers[/bold cyan]\n")

    for tier_key, tier_info in tiers.items():
        # Get profiles for this tier
        tier_profiles = [p for p in pending if p["wikitree_id"] in tier_info["profiles"]]

        if not tier_profiles:
            console.print(f"[dim]{tier_key}: No profiles (all validated)[/dim]")
            continue

        # Create batch data
        batch_data = {
            "generated_at": datetime.now().isoformat(),
            "tier": tier_key,
            "tier_name": tier_info["name"],
            "priority": tier_info["priority"],
            "profile_count": len(tier_profiles),
            "instructions": "For each profile, visit the FamilySearch URL, extract the record data, and fill in the fields below",
            "profiles": []
        }

        for profile in tier_profiles:
            entry = {
                "wikitree_id": profile["wikitree_id"],
                "search_url": profile["search_url"],
                "wikitree_data": profile["wikitree_data"],
                "familysearch_data": {
                    "person_name": "",
                    "birth_date": "",
                    "birth_location": "",
                    "familysearch_record_id": "",
                    "familysearch_url": "",
                    "relationships": {
                        "father": {"name": ""},
                        "mother": {"name": ""}
                    },
                    "source": "FamilySearch",
                    "source_collection": "England, Births and Christenings, 1538-1975",
                    "extraction_confidence": "high",
                    "extraction_method": "manual_entry",
                    "notes": ""
                }
            }
            batch_data["profiles"].append(entry)

        # Save file
        output_file = Path(f"manual_validation_batch_{tier_key}.json")
        with open(output_file, "w") as f:
            json.dump(batch_data, f, indent=2)

        console.print(f"[green]✓[/green] {output_file} ({len(tier_profiles)} profiles)")

    console.print(f"\n[bold]Batch Files Created:[/bold]")
    console.print(f"  • manual_validation_batch_tier1.json - 6 profiles (Priority: HIGH)")
    console.print(f"  • manual_validation_batch_tier2.json - 12 profiles (Priority: MEDIUM)")
    console.print(f"  • manual_validation_batch_tier3.json - 6 profiles (Priority: MEDIUM)")
    console.print(f"  • manual_validation_batch_tier4.json - 2 profiles (Priority: LOW)")

    console.print(f"\n[bold yellow]Validation Strategy:[/bold yellow]")
    console.print(f"1. Start with tier1 (1.5 hours) → 28% validated")
    console.print(f"2. Continue with tier2 (2.5 hours) → 66% validated")
    console.print(f"3. Complete tier3 (1.5 hours) → [green]GPS COMPLIANT (75%+)[/green]")
    console.print(f"4. Optional tier4 for 100% coverage")


if __name__ == "__main__":
    asyncio.run(main())
