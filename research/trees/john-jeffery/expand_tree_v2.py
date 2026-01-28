#!/usr/bin/env python3
"""
Expand family tree with siblings and ancestry - Rate limit safe version.

Features:
- Incremental progress saving
- Graceful rate limit handling
- Resume capability
- Increased wait times between requests
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

import sys
sys.path.insert(0, str(Path(__file__).parent))
from verification import WikiTreeVerifier

console = Console()


class SafeFamilyTreeExpander:
    """Rate-limit-safe family tree expander."""

    def __init__(self, tree_file: Path, progress_file: Path):
        self.tree_file = tree_file
        self.progress_file = progress_file
        self.tree_data = {}
        self.verifier = WikiTreeVerifier()
        self.expanded_profiles = {}
        self.processed_ids = set()
        self.max_generations = 10  # Trace as far back as possible
        self.wait_time = 15  # Increased wait time

    def load_tree(self) -> None:
        """Load existing tree.json."""
        with open(self.tree_file) as f:
            self.tree_data = json.load(f)

    def load_progress(self) -> None:
        """Load previous progress if exists."""
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                data = json.load(f)
                self.expanded_profiles = data.get("profiles", {})
                self.processed_ids = set(data.get("processed_ids", []))
            console.print(f"[yellow]Resumed: {len(self.expanded_profiles)} profiles loaded[/yellow]")

    def save_progress(self) -> None:
        """Save current progress."""
        data = {
            "generated_at": datetime.now().isoformat(),
            "profiles": self.expanded_profiles,
            "processed_ids": list(self.processed_ids),
            "total_profiles": len(self.expanded_profiles),
        }
        with open(self.progress_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    async def fetch_profile_safe(
        self, wikitree_id: str, generation: int = 0
    ) -> Optional[dict]:
        """Fetch profile with rate limit handling."""
        if generation >= self.max_generations:
            return None

        if wikitree_id in self.processed_ids:
            return self.expanded_profiles.get(wikitree_id)

        try:
            params = {
                "action": "getPerson",
                "key": wikitree_id,
                "fields": "Id,Name,FirstName,MiddleName,LastNameAtBirth,LastNameCurrent,"
                         "BirthDate,BirthLocation,DeathDate,DeathLocation,Gender,"
                         "Father,Mother,Parents,Spouses,Children,Siblings",
                "getParents": "1",
                "getChildren": "1",
                "getSpouses": "1",
                "getSiblings": "1",
                "format": "json",
            }

            data = await self.verifier.wikitree._make_wikitree_request(params)

            if not data or len(data) == 0:
                self.processed_ids.add(wikitree_id)
                return None

            profile = data[0].get("person") if "person" in data[0] else data[0]
            self.expanded_profiles[wikitree_id] = profile
            self.processed_ids.add(wikitree_id)

            name = profile.get("BirthName", profile.get("Name", "Unknown"))
            console.print(f"[green]✓[/green] {wikitree_id} - {name} (Gen {generation})")

            # Save progress after each successful fetch
            self.save_progress()

            # Wait to respect rate limits
            await asyncio.sleep(self.wait_time)

            return profile

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                console.print(f"[red]Rate limit hit! Waiting 60 seconds...[/red]")
                await asyncio.sleep(60)
                # Mark as processed to skip in this run
                self.processed_ids.add(wikitree_id)
                return None
            else:
                console.print(f"[yellow]Warning: {wikitree_id}: {e}[/yellow]")
                self.processed_ids.add(wikitree_id)
                return None

    async def trace_ancestors(
        self, wikitree_id: str, generation: int = 0
    ) -> None:
        """Trace ancestors with rate limit safety."""
        profile = await self.fetch_profile_safe(wikitree_id, generation)

        if not profile:
            return

        # Trace father
        father_name = self._get_parent_name(profile, "father")
        if father_name and father_name not in self.processed_ids:
            console.print(f"[blue]→ Father: {father_name}[/blue]")
            await self.trace_ancestors(father_name, generation + 1)

        # Trace mother
        mother_name = self._get_parent_name(profile, "mother")
        if mother_name and mother_name not in self.processed_ids:
            console.print(f"[blue]→ Mother: {mother_name}[/blue]")
            await self.trace_ancestors(mother_name, generation + 1)

    async def expand_tree(self) -> dict:
        """Main expansion with rate limit safety."""
        console.print("\n[bold cyan]═══ Safe Family Tree Expansion ═══[/bold cyan]\n")

        # Get starting profiles
        starting_profiles = []
        for record in self.tree_data.get("records", []):
            if record.get("source") == "WikiTree":
                wt_id = record.get("record_id")
                if wt_id and wt_id not in self.processed_ids:
                    starting_profiles.append(wt_id)

        console.print(f"Profiles to process: {len(starting_profiles)}\n")

        # Process each profile
        for wt_id in starting_profiles:
            console.print(f"\n[cyan]Processing {wt_id}...[/cyan]")
            await self.trace_ancestors(wt_id, generation=0)

        console.print(f"\n[bold green]✓ Expansion complete![/bold green]")
        console.print(f"Total profiles: {len(self.expanded_profiles)}")

        return self.build_tree_structure()

    def _get_parent_name(self, profile: dict, parent_type: str) -> Optional[str]:
        """Safely extract parent name from profile (handles dict or list Parents)."""
        parent_id = profile.get(parent_type.capitalize())
        if not parent_id:
            return None

        parents = profile.get("Parents")
        if not parents:
            return None

        # Handle dict format: {"123": {"Name": "John-123", ...}}
        if isinstance(parents, dict):
            parent_info = parents.get(str(parent_id), {})
            return parent_info.get("Name") if isinstance(parent_info, dict) else None

        # Handle list format: [{"Id": 123, "Name": "John-123", ...}]
        if isinstance(parents, list):
            for parent in parents:
                if parent.get("Id") == parent_id:
                    return parent.get("Name")

        return None

    def build_tree_structure(self) -> dict:
        """Build structured tree output."""
        people = {}

        for wt_id, profile in self.expanded_profiles.items():
            birth_year = ""
            if profile.get("BirthDate"):
                birth_year = profile["BirthDate"].split("-")[0]

            people[wt_id] = {
                "name": profile.get("BirthName", profile.get("Name", "Unknown")),
                "first_name": profile.get("FirstName"),
                "last_name": profile.get("LastNameAtBirth"),
                "birth_date": profile.get("BirthDate"),
                "birth_place": profile.get("BirthLocation"),
                "death_date": profile.get("DeathDate"),
                "death_place": profile.get("DeathLocation"),
                "gender": profile.get("Gender"),
                "father": self._get_parent_name(profile, "father"),
                "mother": self._get_parent_name(profile, "mother"),
                "siblings": list(profile.get("Siblings", {}).keys()) if isinstance(profile.get("Siblings"), dict) else [],
                "spouses": list(profile.get("Spouses", {}).keys()) if isinstance(profile.get("Spouses"), dict) else [],
                "children": list(profile.get("Children", {}).keys()) if isinstance(profile.get("Children"), dict) else [],
            }

        return {
            "generated_at": datetime.now().isoformat(),
            "expansion_type": "safe_ancestry_expansion",
            "total_profiles": len(people),
            "max_generations_traced": self.max_generations,
            "people": people,
        }

    def save_final_tree(self, output_file: Path, tree_structure: dict) -> None:
        """Save final tree structure."""
        with open(output_file, "w") as f:
            json.dump(tree_structure, f, indent=2, default=str)
        console.print(f"\n[green]✓[/green] Saved to {output_file}")


async def main():
    """Main execution."""
    tree_file = Path("tree.json")
    progress_file = Path("expansion_progress.json")
    output_file = Path("expanded_tree.json")

    if not tree_file.exists():
        console.print(f"[red]Error: {tree_file} not found[/red]")
        return

    expander = SafeFamilyTreeExpander(tree_file, progress_file)
    expander.load_tree()
    expander.load_progress()

    try:
        tree_structure = await expander.expand_tree()
        expander.save_final_tree(output_file, tree_structure)

        # Print summary
        console.print("\n[bold cyan]═══ Summary ═══[/bold cyan]\n")
        console.print(f"Total profiles fetched: {tree_structure['total_profiles']}")
        console.print(f"Max generations traced: {tree_structure['max_generations_traced']}")

        # Print some sample ancestry
        console.print("\n[bold]Sample Ancestry:[/bold]\n")
        for wt_id, person in list(tree_structure["people"].items())[:5]:
            console.print(f"  • {person['name']} (b. {person.get('birth_date', 'unknown')})")
            if person.get("father"):
                console.print(f"    Father: {person['father']}")
            if person.get("mother"):
                console.print(f"    Mother: {person['mother']}")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted! Progress saved.[/yellow]")
        expander.save_progress()


if __name__ == "__main__":
    asyncio.run(main())
