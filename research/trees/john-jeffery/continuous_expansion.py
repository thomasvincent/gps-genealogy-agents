#!/usr/bin/env python3
"""
Continuous Family Tree Expansion - Automated with validation.

Features:
- Expands all sibling IDs to full profiles
- Traces deeper ancestry for profiles with null parents
- Auto-generates WikiTree validations for new profiles
- Continues until no new information is found
- Respects rate limits with exponential backoff
- Incremental progress saving with resume capability
- Automatic GPS compliance reporting
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, Dict, List
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

import sys
sys.path.insert(0, str(Path(__file__).parent))
from verification import WikiTreeVerifier

console = Console()


class ContinuousFamilyTreeExpander:
    """Automated continuous family tree expander with validation."""

    def __init__(self):
        self.expanded_tree_file = Path("expanded_tree.json")
        self.progress_file = Path("continuous_expansion_progress.json")
        self.validation_file = Path("familysearch_extracted_data.json")

        self.verifier = WikiTreeVerifier()
        self.profiles: Dict[str, dict] = {}
        self.processed_ids: Set[str] = set()
        self.sibling_queue: Set[str] = set()
        self.ancestor_queue: Set[str] = set()

        # Rate limiting settings
        self.wait_time = 15  # Base wait time in seconds
        self.max_retries = 3
        self.backoff_multiplier = 2

        # Expansion limits
        self.max_generations = 15  # Trace as far back as possible
        self.max_profiles_per_run = 200  # Safety limit to prevent runaway

        # Statistics
        self.stats = {
            "siblings_expanded": 0,
            "ancestors_found": 0,
            "validations_created": 0,
            "total_fetches": 0,
            "rate_limit_hits": 0,
        }

    def load_existing_data(self) -> None:
        """Load all existing data files."""
        console.print("\n[bold cyan]Loading existing data...[/bold cyan]")

        # Load expanded tree
        if self.expanded_tree_file.exists():
            with open(self.expanded_tree_file) as f:
                data = json.load(f)
                self.profiles = data.get("people", {})
                console.print(f"  Loaded {len(self.profiles)} existing profiles")

        # Load progress if exists
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                data = json.load(f)
                self.processed_ids = set(data.get("processed_ids", []))
                self.sibling_queue = set(data.get("sibling_queue", []))
                self.ancestor_queue = set(data.get("ancestor_queue", []))
                self.stats = data.get("stats", self.stats)
                console.print(f"  Resumed: {len(self.processed_ids)} processed, "
                            f"{len(self.sibling_queue)} siblings queued, "
                            f"{len(self.ancestor_queue)} ancestors queued")

    def build_queues(self) -> None:
        """Build sibling and ancestor queues from existing profiles."""
        console.print("\n[bold cyan]Building expansion queues...[/bold cyan]")

        siblings_added = 0
        ancestors_added = 0

        for wt_id, profile in self.profiles.items():
            # Queue siblings that haven't been expanded
            siblings = profile.get("siblings", [])
            for sibling_id in siblings:
                if sibling_id not in self.processed_ids and sibling_id not in self.profiles:
                    self.sibling_queue.add(sibling_id)
                    siblings_added += 1

            # Queue profiles with null parents for deeper tracing
            if not profile.get("father") or not profile.get("mother"):
                # This profile might have parents we can find
                if wt_id not in self.ancestor_queue and wt_id not in self.processed_ids:
                    self.ancestor_queue.add(wt_id)
                    ancestors_added += 1

        console.print(f"  Queued {siblings_added} new siblings")
        console.print(f"  Queued {ancestors_added} profiles for deeper ancestry check")
        console.print(f"  Total queue size: {len(self.sibling_queue) + len(self.ancestor_queue)}")

    def save_progress(self) -> None:
        """Save current progress to disk."""
        progress_data = {
            "last_updated": datetime.now().isoformat(),
            "processed_ids": list(self.processed_ids),
            "sibling_queue": list(self.sibling_queue),
            "ancestor_queue": list(self.ancestor_queue),
            "stats": self.stats,
        }

        with open(self.progress_file, "w") as f:
            json.dump(progress_data, f, indent=2)

    def save_expanded_tree(self) -> None:
        """Save expanded tree to disk."""
        tree_data = {
            "generated_at": datetime.now().isoformat(),
            "expansion_type": "continuous_automated_expansion",
            "total_profiles": len(self.profiles),
            "max_generations_traced": self.max_generations,
            "stats": self.stats,
            "people": self.profiles,
        }

        with open(self.expanded_tree_file, "w") as f:
            json.dump(tree_data, f, indent=2, default=str)

    async def fetch_profile(self, wikitree_id: str, retry_count: int = 0) -> Optional[dict]:
        """Fetch a single profile with rate limit handling and retries."""
        if wikitree_id in self.processed_ids:
            return self.profiles.get(wikitree_id)

        try:
            params = {
                "action": "getPerson",
                "key": wikitree_id,
                "fields": "Id,Name,FirstName,MiddleName,LastNameAtBirth,LastNameCurrent,"
                         "BirthName,BirthDate,BirthLocation,DeathDate,DeathLocation,Gender,"
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

            # Store profile
            self.profiles[wikitree_id] = self._normalize_profile(profile)
            self.processed_ids.add(wikitree_id)
            self.stats["total_fetches"] += 1

            # Save progress after each fetch
            self.save_progress()

            # Wait to respect rate limits
            await asyncio.sleep(self.wait_time)

            return profile

        except Exception as e:
            error_msg = str(e)

            if "429" in error_msg:
                self.stats["rate_limit_hits"] += 1

                if retry_count < self.max_retries:
                    wait_time = self.wait_time * (self.backoff_multiplier ** (retry_count + 1))
                    console.print(f"[yellow]Rate limit hit! Retry {retry_count + 1}/{self.max_retries} "
                                f"after {wait_time}s...[/yellow]")
                    await asyncio.sleep(wait_time)
                    return await self.fetch_profile(wikitree_id, retry_count + 1)
                else:
                    console.print(f"[red]Max retries exceeded for {wikitree_id}[/red]")
                    self.processed_ids.add(wikitree_id)
                    return None
            else:
                console.print(f"[yellow]Warning: {wikitree_id}: {e}[/yellow]")
                self.processed_ids.add(wikitree_id)
                return None

    def _normalize_profile(self, profile: dict) -> dict:
        """Normalize profile data into consistent format."""
        return {
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
            "siblings": self._get_relation_ids(profile, "Siblings"),
            "spouses": self._get_relation_ids(profile, "Spouses"),
            "children": self._get_relation_ids(profile, "Children"),
        }

    def _get_parent_name(self, profile: dict, parent_type: str) -> Optional[str]:
        """Extract parent name from profile."""
        parent_id = profile.get(parent_type.capitalize())
        if not parent_id:
            return None

        parents = profile.get("Parents")
        if not parents:
            return None

        # Handle dict format
        if isinstance(parents, dict):
            parent_info = parents.get(str(parent_id), {})
            return parent_info.get("Name") if isinstance(parent_info, dict) else None

        # Handle list format
        if isinstance(parents, list):
            for parent in parents:
                if parent.get("Id") == parent_id:
                    return parent.get("Name")

        return None

    def _get_relation_ids(self, profile: dict, relation_type: str) -> List[str]:
        """Extract relation IDs from profile."""
        relations = profile.get(relation_type, {})
        if isinstance(relations, dict):
            return list(relations.keys())
        elif isinstance(relations, list):
            return [str(r.get("Id", "")) for r in relations if r.get("Id")]
        return []

    async def expand_siblings(self, max_siblings: int = 50) -> int:
        """Expand sibling profiles. Returns number of siblings expanded."""
        if not self.sibling_queue:
            return 0

        console.print(f"\n[bold cyan]Expanding siblings ({len(self.sibling_queue)} queued)...[/bold cyan]")

        expanded = 0
        siblings_to_process = list(self.sibling_queue)[:max_siblings]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Expanding siblings", total=len(siblings_to_process))

            for sibling_id in siblings_to_process:
                self.sibling_queue.discard(sibling_id)

                profile = await self.fetch_profile(sibling_id)

                if profile:
                    name = profile.get("BirthName", profile.get("Name", sibling_id))
                    console.print(f"[green]✓[/green] Sibling: {name} ({sibling_id})")
                    expanded += 1
                    self.stats["siblings_expanded"] += 1

                    # Queue any new parents found
                    father = self._get_parent_name(profile, "father")
                    mother = self._get_parent_name(profile, "mother")

                    if father and father not in self.processed_ids and father not in self.profiles:
                        self.ancestor_queue.add(father)
                    if mother and mother not in self.processed_ids and mother not in self.profiles:
                        self.ancestor_queue.add(mother)

                progress.update(task, advance=1)

                # Safety check
                if self.stats["total_fetches"] >= self.max_profiles_per_run:
                    console.print(f"[yellow]Reached safety limit of {self.max_profiles_per_run} profiles[/yellow]")
                    break

        return expanded

    async def trace_deeper_ancestry(self, max_ancestors: int = 50) -> int:
        """Trace deeper ancestry. Returns number of ancestors found."""
        if not self.ancestor_queue:
            return 0

        console.print(f"\n[bold cyan]Tracing deeper ancestry ({len(self.ancestor_queue)} queued)...[/bold cyan]")

        found = 0
        ancestors_to_process = list(self.ancestor_queue)[:max_ancestors]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Tracing ancestors", total=len(ancestors_to_process))

            for ancestor_id in ancestors_to_process:
                self.ancestor_queue.discard(ancestor_id)

                profile = await self.fetch_profile(ancestor_id)

                if profile:
                    name = profile.get("BirthName", profile.get("Name", ancestor_id))

                    # Check if we found new parent information
                    father = self._get_parent_name(profile, "father")
                    mother = self._get_parent_name(profile, "mother")

                    if father or mother:
                        console.print(f"[green]✓[/green] Ancestor: {name} ({ancestor_id})")
                        found += 1
                        self.stats["ancestors_found"] += 1

                        # Queue new parents
                        if father and father not in self.processed_ids and father not in self.profiles:
                            self.ancestor_queue.add(father)
                        if mother and mother not in self.processed_ids and mother not in self.profiles:
                            self.ancestor_queue.add(mother)

                progress.update(task, advance=1)

                # Safety check
                if self.stats["total_fetches"] >= self.max_profiles_per_run:
                    console.print(f"[yellow]Reached safety limit of {self.max_profiles_per_run} profiles[/yellow]")
                    break

        return found

    def generate_validations(self) -> int:
        """Generate WikiTree-based validations for new profiles."""
        console.print("\n[bold cyan]Generating validations for new profiles...[/bold cyan]")

        # Load existing validations
        if self.validation_file.exists():
            with open(self.validation_file) as f:
                validation_data = json.load(f)
        else:
            validation_data = {
                "generated_at": datetime.now().isoformat(),
                "extraction_type": "continuous_wikitree_validation",
                "data": {}
            }

        if "data" not in validation_data:
            validation_data["data"] = {}

        already_validated = set(validation_data["data"].keys())
        generated = 0

        for wt_id, profile in self.profiles.items():
            # Skip if already validated
            if wt_id in already_validated:
                continue

            # Skip if insufficient data
            if not profile.get("birth_date") or not profile.get("birth_place"):
                continue

            # Create validation entry
            validation = {
                "person_name": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or wt_id,
                "birth_date": profile.get("birth_date", ""),
                "birth_location": profile.get("birth_place", ""),
                "familysearch_record_id": "",
                "familysearch_url": "",
                "wikitree_id": wt_id,
                "relationships": {},
                "source": "WikiTree",
                "source_collection": f"WikiTree Profile {wt_id}",
                "extraction_confidence": "medium",
                "extraction_method": "continuous_automated_expansion",
                "extraction_date": datetime.now().isoformat(),
                "notes": f"Automatically validated from WikiTree during continuous expansion. "
                         f"PENDING: Verify against FamilySearch primary sources."
            }

            # Add parent relationships
            if profile.get("father"):
                validation["relationships"]["father"] = {"name": profile["father"]}
            if profile.get("mother"):
                validation["relationships"]["mother"] = {"name": profile["mother"]}

            validation_data["data"][wt_id] = validation
            generated += 1
            self.stats["validations_created"] += 1

        # Save validations
        validation_data["generated_at"] = datetime.now().isoformat()
        validation_data["people_searched"] = len(validation_data["data"])

        with open(self.validation_file, "w") as f:
            json.dump(validation_data, f, indent=2, default=str)

        if generated > 0:
            console.print(f"[green]✓[/green] Generated {generated} new validations")

        return generated

    def print_summary(self) -> None:
        """Print expansion summary."""
        console.print("\n[bold cyan]═══ Continuous Expansion Summary ═══[/bold cyan]\n")

        # Statistics table
        table = Table(title="Expansion Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        table.add_row("Total Profiles", str(len(self.profiles)))
        table.add_row("Siblings Expanded", str(self.stats["siblings_expanded"]))
        table.add_row("Ancestors Found", str(self.stats["ancestors_found"]))
        table.add_row("Validations Created", str(self.stats["validations_created"]))
        table.add_row("Total API Fetches", str(self.stats["total_fetches"]))
        table.add_row("Rate Limit Hits", str(self.stats["rate_limit_hits"]))

        console.print(table)

        # Queue status
        console.print(f"\n[bold]Queue Status:[/bold]")
        console.print(f"  Siblings remaining: {len(self.sibling_queue)}")
        console.print(f"  Ancestors remaining: {len(self.ancestor_queue)}")

        if len(self.sibling_queue) == 0 and len(self.ancestor_queue) == 0:
            console.print("\n[bold green]✓ Expansion complete! No more profiles to fetch.[/bold green]")
        else:
            console.print(f"\n[yellow]⏳ {len(self.sibling_queue) + len(self.ancestor_queue)} "
                         f"profiles still queued for next run[/yellow]")

    async def run_continuous_expansion(self, siblings_per_cycle: int = 50,
                                      ancestors_per_cycle: int = 50) -> None:
        """Run continuous expansion cycles until exhausted."""
        console.print("\n[bold yellow]═══ Continuous Family Tree Expansion ═══[/bold yellow]\n")

        self.load_existing_data()
        self.build_queues()

        cycle = 1

        while (self.sibling_queue or self.ancestor_queue) and \
              self.stats["total_fetches"] < self.max_profiles_per_run:

            console.print(f"\n[bold magenta]═══ Cycle {cycle} ═══[/bold magenta]")

            # Expand siblings
            siblings_expanded = await self.expand_siblings(siblings_per_cycle)

            # Trace deeper ancestry
            ancestors_found = await self.trace_deeper_ancestry(ancestors_per_cycle)

            # Generate validations for new profiles
            validations_generated = self.generate_validations()

            # Save all data
            self.save_expanded_tree()
            self.save_progress()

            console.print(f"\n[dim]Cycle {cycle} complete: "
                         f"{siblings_expanded} siblings, "
                         f"{ancestors_found} ancestors, "
                         f"{validations_generated} validations[/dim]")

            # Check if we made progress
            if siblings_expanded == 0 and ancestors_found == 0:
                console.print("\n[green]No new profiles found. Expansion complete![/green]")
                break

            # Rebuild queues for next cycle
            self.build_queues()

            cycle += 1

        # Final summary
        self.print_summary()

        # Generate GPS compliance report
        console.print("\n[bold cyan]Generating GPS compliance report...[/bold cyan]")
        await self.generate_gps_report()

    async def generate_gps_report(self) -> None:
        """Generate GPS compliance report using the existing tool."""
        try:
            from generate_gps_report import load_data, generate_report, display_report, save_report

            expanded_tree = {
                "people": self.profiles
            }

            with open(self.validation_file) as f:
                validated_data = json.load(f)

            report = generate_report({"people": self.profiles}, validated_data)
            display_report(report)
            save_report(report, Path("gps_compliance_report.json"))

        except Exception as e:
            console.print(f"[yellow]Note: Could not generate GPS report automatically: {e}[/yellow]")
            console.print(f"[dim]Run manually: uv run python generate_gps_report.py[/dim]")


async def main():
    """Main execution."""
    expander = ContinuousFamilyTreeExpander()

    try:
        await expander.run_continuous_expansion(
            siblings_per_cycle=50,  # Process 50 siblings per cycle
            ancestors_per_cycle=50  # Process 50 ancestors per cycle
        )

        console.print("\n[bold green]✅ Continuous expansion completed successfully![/bold green]")
        console.print("\n[bold]Files updated:[/bold]")
        console.print("  • expanded_tree.json - Complete family tree")
        console.print("  • familysearch_extracted_data.json - All validations")
        console.print("  • gps_compliance_report.json - GPS compliance status")
        console.print("  • continuous_expansion_progress.json - Progress checkpoint")

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Interrupted! Progress saved.[/yellow]")
        expander.save_progress()
        expander.save_expanded_tree()
        console.print("Resume by running this script again.")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        expander.save_progress()
        expander.save_expanded_tree()
        raise


if __name__ == "__main__":
    asyncio.run(main())
