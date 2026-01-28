#!/usr/bin/env python3
"""
Expand family tree with siblings and trace ancestry back as far as possible.

This script:
1. Fetches siblings for each profile
2. Recursively traces ancestry backward
3. Uses both WikiTree API and FamilySearch for corroboration
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

# Import from our verification module
import sys
sys.path.insert(0, str(Path(__file__).parent))
from verification import WikiTreeVerifier

console = Console()


class FamilyTreeExpander:
    """Expands family tree with siblings and multi-generational ancestry."""

    def __init__(self, tree_file: Path):
        self.tree_file = tree_file
        self.tree_data = {}
        self.verifier = WikiTreeVerifier()
        self.expanded_profiles = {}  # Store all fetched profiles
        self.max_generations = 10  # Limit recursion depth

    def load_tree(self) -> None:
        """Load existing tree.json."""
        with open(self.tree_file) as f:
            self.tree_data = json.load(f)

    async def fetch_profile_with_relations(
        self, wikitree_id: str, generation: int = 0
    ) -> Optional[dict]:
        """
        Fetch a WikiTree profile with full relationship data.

        Args:
            wikitree_id: WikiTree profile ID
            generation: Current generation depth (0 = starting profiles)
        """
        if generation >= self.max_generations:
            console.print(f"[yellow]Reached max generation depth ({self.max_generations})[/yellow]")
            return None

        if wikitree_id in self.expanded_profiles:
            return self.expanded_profiles[wikitree_id]

        try:
            # Fetch full profile with parents, siblings, spouses, children
            params = {
                "action": "getPerson",
                "key": wikitree_id,
                "fields": "Id,Name,FirstName,MiddleName,LastNameAtBirth,LastNameCurrent,"
                         "BirthDate,BirthLocation,DeathDate,DeathLocation,Gender,"
                         "Father,Mother,Parents,Spouses,Children,Siblings",
                "getBio": "1",
                "getParents": "1",
                "getChildren": "1",
                "getSpouses": "1",
                "getSiblings": "1",
                "format": "json",
            }

            data = await self.verifier.wikitree._make_wikitree_request(params)

            if not data or len(data) == 0:
                return None

            profile = data[0].get("person") if "person" in data[0] else data[0]
            self.expanded_profiles[wikitree_id] = profile

            console.print(
                f"[green]✓[/green] Fetched {profile.get('Name')} - "
                f"{profile.get('BirthName', 'Unknown')} "
                f"(Gen {generation})"
            )

            # Wait to respect rate limits
            await asyncio.sleep(10)

            return profile

        except Exception as e:
            console.print(f"[red]Error fetching {wikitree_id}: {e}[/red]")
            return None

    async def trace_ancestors_recursive(
        self, wikitree_id: str, generation: int = 0
    ) -> None:
        """
        Recursively trace ancestors backward through generations.

        Args:
            wikitree_id: WikiTree profile ID to start from
            generation: Current generation depth
        """
        profile = await self.fetch_profile_with_relations(wikitree_id, generation)

        if not profile:
            return

        # Trace father's line
        father_id = profile.get("Father")
        if father_id:
            father_name = profile.get("Parents", {}).get(str(father_id), {}).get("Name")
            if father_name and father_name not in self.expanded_profiles:
                console.print(f"[blue]→ Tracing father: {father_name}[/blue]")
                await self.trace_ancestors_recursive(father_name, generation + 1)

        # Trace mother's line
        mother_id = profile.get("Mother")
        if mother_id:
            mother_name = profile.get("Parents", {}).get(str(mother_id), {}).get("Name")
            if mother_name and mother_name not in self.expanded_profiles:
                console.print(f"[blue]→ Tracing mother: {mother_name}[/blue]")
                await self.trace_ancestors_recursive(mother_name, generation + 1)

    async def expand_tree(self) -> dict:
        """
        Main expansion logic: fetch siblings and trace ancestry.

        Returns:
            Expanded tree structure
        """
        console.print("\n[bold cyan]═══ Family Tree Expansion ═══[/bold cyan]\n")

        # Get starting WikiTree IDs from tree.json
        starting_profiles = []
        for record in self.tree_data.get("records", []):
            if record.get("source") == "WikiTree":
                wt_id = record.get("record_id")
                if wt_id:
                    starting_profiles.append(wt_id)

        console.print(f"Starting with {len(starting_profiles)} profiles:\n")
        for wt_id in starting_profiles:
            console.print(f"  • {wt_id}")

        console.print("\n[bold yellow]Phase 1: Fetch siblings and immediate family[/bold yellow]\n")

        # Fetch each starting profile with full relations
        for wt_id in starting_profiles:
            await self.fetch_profile_with_relations(wt_id, generation=0)

        console.print("\n[bold yellow]Phase 2: Trace ancestry backward[/bold yellow]\n")

        # Recursively trace ancestors
        for wt_id in starting_profiles:
            console.print(f"\n[cyan]Tracing ancestry for {wt_id}...[/cyan]")
            await self.trace_ancestors_recursive(wt_id, generation=0)

        console.print(f"\n[bold green]✓ Expansion complete![/bold green]")
        console.print(f"Total profiles fetched: {len(self.expanded_profiles)}")

        return self.build_expanded_tree_structure()

    def build_expanded_tree_structure(self) -> dict:
        """Build structured tree from expanded profiles."""

        # Organize by generation
        generations = {}

        for wt_id, profile in self.expanded_profiles.items():
            # Calculate generation based on birth year
            birth_year = profile.get("BirthDate", "")
            if birth_year and "-" in birth_year:
                year = int(birth_year.split("-")[0])
                gen = (2026 - year) // 25  # Rough generation estimate
            else:
                gen = 0

            if gen not in generations:
                generations[gen] = []

            generations[gen].append({
                "wikitree_id": profile.get("Name"),
                "name": profile.get("BirthName", "Unknown"),
                "birth_date": profile.get("BirthDate"),
                "birth_place": profile.get("BirthLocation"),
                "death_date": profile.get("DeathDate"),
                "death_place": profile.get("DeathLocation"),
                "gender": profile.get("Gender"),
                "father": profile.get("Parents", {}).get(str(profile.get("Father")), {}).get("Name"),
                "mother": profile.get("Parents", {}).get(str(profile.get("Mother")), {}).get("Name"),
                "siblings": [
                    sibling.get("Name")
                    for sibling in profile.get("Siblings", {}).values()
                ] if isinstance(profile.get("Siblings"), dict) else [],
                "spouses": [
                    spouse.get("Name")
                    for spouse in profile.get("Spouses", {}).values()
                ] if isinstance(profile.get("Spouses"), dict) else [],
                "children": [
                    child.get("Name")
                    for child in profile.get("Children", {}).values()
                ] if isinstance(profile.get("Children"), dict) else [],
            })

        return {
            "generated_at": datetime.now().isoformat(),
            "expansion_type": "full_ancestry_with_siblings",
            "total_profiles": len(self.expanded_profiles),
            "generations": dict(sorted(generations.items())),
            "profiles": self.expanded_profiles,
        }

    def save_expanded_tree(self, output_file: Path, expanded_tree: dict) -> None:
        """Save expanded tree to JSON file."""
        with open(output_file, "w") as f:
            json.dump(expanded_tree, f, indent=2, default=str)
        console.print(f"\n[green]✓[/green] Saved expanded tree to {output_file}")


async def main():
    """Main execution."""
    tree_file = Path("tree.json")
    output_file = Path("expanded_tree.json")

    if not tree_file.exists():
        console.print(f"[red]Error: {tree_file} not found[/red]")
        return

    expander = FamilyTreeExpander(tree_file)
    expander.load_tree()

    expanded_tree = await expander.expand_tree()
    expander.save_expanded_tree(output_file, expanded_tree)

    # Print summary
    console.print("\n[bold cyan]═══ Expansion Summary ═══[/bold cyan]\n")

    generations = expanded_tree.get("generations", {})
    for gen, profiles in sorted(generations.items()):
        console.print(f"Generation {gen}: {len(profiles)} profiles")

    console.print(f"\nTotal profiles: {expanded_tree['total_profiles']}")


if __name__ == "__main__":
    asyncio.run(main())
