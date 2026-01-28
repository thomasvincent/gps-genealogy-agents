#!/usr/bin/env python3
"""
Validate expanded ancestry with primary sources (FamilySearch).

This script:
1. Loads all 32 profiles from expanded_tree.json
2. For each profile, searches FamilySearch for christening/birth records
3. Cross-references data between WikiTree and FamilySearch
4. Generates GPS Pillar 3 compliance report
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

console = Console()


class AncestryValidator:
    """Validates ancestry records against primary sources."""

    def __init__(self, expanded_tree_file: Path):
        self.expanded_tree_file = expanded_tree_file
        self.tree_data = {}
        self.validation_results = {}
        self.familysearch_data = {}

    def load_expanded_tree(self) -> None:
        """Load expanded_tree.json."""
        with open(self.expanded_tree_file) as f:
            self.tree_data = json.load(f)
        console.print(f"[green]✓[/green] Loaded {self.tree_data['total_profiles']} profiles")

    def analyze_validation_needs(self) -> list[dict]:
        """Determine which profiles need validation."""
        profiles_to_validate = []

        for wt_id, person in self.tree_data["people"].items():
            # Skip if no birth information
            if not person.get("birth_date") or not person.get("birth_place"):
                continue

            # Skip if already validated (from previous runs)
            if wt_id in self.familysearch_data:
                continue

            profile_data = {
                "wikitree_id": wt_id,
                "name": person["name"],
                "first_name": person.get("first_name"),
                "last_name": person.get("last_name"),
                "birth_date": person.get("birth_date"),
                "birth_place": person.get("birth_place"),
                "father": person.get("father"),
                "mother": person.get("mother"),
            }

            # Add FamilySearch search URL
            profile_data["familysearch_search_url"] = self._generate_familysearch_search_url(profile_data)

            profiles_to_validate.append(profile_data)

        return profiles_to_validate

    async def validate_with_familysearch(self, profile: dict) -> dict:
        """
        Validate a single profile with FamilySearch.

        NOTE: This requires manual interaction via Playwright MCP tools.
        For automated validation of 32 profiles, we'll need to:
        1. Use the existing familysearch_login.py Playwright automation
        2. Or create a batch search tool
        3. Or provide search URLs for manual extraction
        """
        console.print(f"\n[cyan]Validating: {profile['name']}[/cyan]")
        console.print(f"  WikiTree ID: {profile['wikitree_id']}")
        console.print(f"  Born: {profile['birth_date']} in {profile['birth_place']}")

        # Generate FamilySearch search URL
        search_url = self._generate_familysearch_search_url(profile)
        console.print(f"  Search URL: {search_url}")

        return {
            "wikitree_id": profile["wikitree_id"],
            "search_url": search_url,
            "status": "pending_manual_search",
            "wikitree_data": profile,
        }

    def _generate_familysearch_search_url(self, profile: dict) -> str:
        """Generate FamilySearch search URL for a profile."""
        base_url = "https://www.familysearch.org/search/record/results"

        # Extract location parts
        birth_place = profile.get("birth_place", "")
        place_parts = [p.strip() for p in birth_place.split(",")]

        # Extract birth year
        birth_date = profile.get("birth_date", "")
        birth_year = birth_date.split("-")[0] if birth_date else ""

        # Build search parameters
        params = []
        if profile.get("first_name"):
            params.append(f"givenName={profile['first_name'].replace(' ', '+')}")
        if profile.get("last_name"):
            params.append(f"surname={profile['last_name'].replace(' ', '+')}")
        if birth_year:
            params.append(f"birthLikeYear={birth_year}")
            params.append(f"birthLikePlace={'+'.join(place_parts[:2])}")  # First 2 place parts

        query_string = "&".join(params)
        return f"{base_url}?{query_string}"

    def generate_validation_report(self, profiles_to_validate: list[dict]) -> dict:
        """Generate report with search URLs for manual validation."""
        return {
            "generated_at": datetime.now().isoformat(),
            "total_profiles": self.tree_data["total_profiles"],
            "profiles_needing_validation": len(profiles_to_validate),
            "validation_method": "familysearch_manual_search",
            "profiles": profiles_to_validate,
        }

    def save_validation_report(self, report: dict, output_file: Path) -> None:
        """Save validation report."""
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2, default=str)
        console.print(f"\n[green]✓[/green] Saved validation report to {output_file}")


async def main():
    """Main execution."""
    expanded_tree_file = Path("expanded_tree.json")
    output_file = Path("ancestry_validation_plan.json")

    if not expanded_tree_file.exists():
        console.print(f"[red]Error: {expanded_tree_file} not found[/red]")
        return

    validator = AncestryValidator(expanded_tree_file)
    validator.load_expanded_tree()

    console.print("\n[bold cyan]═══ Ancestry Validation Plan ═══[/bold cyan]\n")

    # Analyze which profiles need validation
    profiles_to_validate = validator.analyze_validation_needs()

    console.print(f"Profiles requiring validation: {len(profiles_to_validate)}\n")

    # Display summary table
    table = Table(title="Profiles to Validate")
    table.add_column("WikiTree ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Birth", style="yellow")
    table.add_column("Location", style="magenta")

    for profile in profiles_to_validate[:10]:  # Show first 10
        table.add_row(
            profile["wikitree_id"],
            profile["name"],
            profile.get("birth_date", "Unknown"),
            profile.get("birth_place", "Unknown")[:40],
        )

    console.print(table)

    if len(profiles_to_validate) > 10:
        console.print(f"\n[yellow]... and {len(profiles_to_validate) - 10} more[/yellow]")

    # Generate validation report with search URLs
    report = validator.generate_validation_report(profiles_to_validate)
    validator.save_validation_report(report, output_file)

    console.print("\n[bold yellow]Next Steps:[/bold yellow]")
    console.print("1. Review ancestry_validation_plan.json")
    console.print("2. Use FamilySearch search URLs for each profile")
    console.print("3. Extract christening/birth records")
    console.print("4. Compare with WikiTree data")
    console.print("5. Generate GPS Pillar 3 compliance report")


if __name__ == "__main__":
    asyncio.run(main())
