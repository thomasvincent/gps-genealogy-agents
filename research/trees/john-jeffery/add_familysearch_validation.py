#!/usr/bin/env python3
"""
Interactive tool to add FamilySearch validation data for remaining 26 profiles.

Usage:
    uv run python add_familysearch_validation.py

For each profile, you'll be prompted to enter:
- FamilySearch record URL
- Birth/christening date from record
- Birth/christening location from record
- Father's name from record
- Mother's name from record
- Source collection name
- Any notes
"""

import json
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

console = Console()


class FamilySearchDataEntry:
    """Interactive data entry for FamilySearch validation."""

    def __init__(self, extracted_data_file: Path, validation_results_file: Path):
        self.extracted_data_file = extracted_data_file
        self.validation_results_file = validation_results_file
        self.extracted_data = {}
        self.validation_results = {}
        self.profiles_to_validate = []

    def load_existing_data(self) -> None:
        """Load existing FamilySearch data."""
        if self.extracted_data_file.exists():
            with open(self.extracted_data_file) as f:
                self.extracted_data = json.load(f)
            console.print(
                f"[green]✓[/green] Loaded {len(self.extracted_data.get('data', {}))} existing validations"
            )

        with open(self.validation_results_file) as f:
            self.validation_results = json.load(f)

    def identify_profiles_to_validate(self) -> list[dict]:
        """Find profiles that need validation."""
        already_validated = set(self.extracted_data.get("data", {}).keys())

        profiles_needing_validation = []
        for wt_id, profile in self.validation_results["validated_profiles"].items():
            if wt_id not in already_validated:
                profiles_needing_validation.append({
                    "wikitree_id": wt_id,
                    "name": profile["wikitree_data"]["name"],
                    "birth_date": profile["wikitree_data"]["birth_date"],
                    "birth_place": profile["wikitree_data"]["birth_place"],
                    "father": profile["wikitree_data"].get("father"),
                    "mother": profile["wikitree_data"].get("mother"),
                    "search_url": profile["familysearch_search_url"],
                })

        return profiles_needing_validation

    def show_profile_info(self, profile: dict) -> None:
        """Display profile information."""
        console.print(f"\n[bold cyan]Profile: {profile['name']}[/bold cyan]")
        console.print(f"WikiTree ID: {profile['wikitree_id']}")
        console.print(f"Birth: {profile['birth_date']} in {profile['birth_place']}")
        if profile['father']:
            console.print(f"Father (WikiTree): {profile['father']}")
        if profile['mother']:
            console.print(f"Mother (WikiTree): {profile['mother']}")
        console.print(f"\nSearch URL: [link]{profile['search_url']}[/link]\n")

    def enter_familysearch_data(self, profile: dict) -> dict:
        """Interactive data entry for a profile."""
        console.print("[yellow]Enter FamilySearch record data (or 'skip' to skip):[/yellow]\n")

        # Check if user found a record
        found_record = Confirm.ask("Did you find a matching FamilySearch record?", default=True)

        if not found_record:
            console.print("[yellow]Skipping - no record found[/yellow]")
            return {
                "validation_status": "no_record_found",
                "notes": "No matching FamilySearch record found"
            }

        # Record URL
        record_url = Prompt.ask(
            "FamilySearch record URL",
            default=""
        )

        # Extract record ID from URL if present
        record_id = ""
        if "familysearch.org" in record_url and ":1:" in record_url:
            record_id = record_url.split(":1:")[-1].split("?")[0]

        # Person name from record
        person_name = Prompt.ask(
            "Person name (as shown in record)",
            default=profile['name']
        )

        # Birth/christening date
        event_date = Prompt.ask(
            "Birth/christening date",
            default=profile['birth_date']
        )

        # Birth/christening location
        event_location = Prompt.ask(
            "Birth/christening location",
            default=profile['birth_place']
        )

        # Father's name
        father_name = Prompt.ask(
            "Father's name (from record)",
            default=profile.get('father', '')
        )

        # Mother's name
        mother_name = Prompt.ask(
            "Mother's name (from record)",
            default=profile.get('mother', '')
        )

        # Source collection
        source_collection = Prompt.ask(
            "Source collection",
            default="England, Births and Christenings, 1538-1975"
        )

        # Confidence
        confidence = Prompt.ask(
            "Extraction confidence",
            choices=["high", "medium", "low"],
            default="high"
        )

        # Notes
        notes = Prompt.ask(
            "Notes (optional)",
            default=""
        )

        # Build FamilySearch data entry
        fs_data = {
            "person_name": person_name,
            "birth_date": event_date,
            "birth_location": event_location,
            "familysearch_record_id": record_id,
            "familysearch_url": record_url,
            "wikitree_id": profile['wikitree_id'],
            "relationships": {
                "father": {"name": father_name} if father_name else None,
                "mother": {"name": mother_name} if mother_name else None,
            },
            "source": "FamilySearch",
            "source_collection": source_collection,
            "extraction_confidence": confidence,
            "extraction_method": "manual_entry",
            "extraction_date": datetime.now().isoformat(),
            "notes": notes or f"Manual validation entry for {profile['wikitree_id']}",
        }

        # Remove None values
        if fs_data["relationships"]["father"] is None:
            del fs_data["relationships"]["father"]
        if fs_data["relationships"]["mother"] is None:
            del fs_data["relationships"]["mother"]

        return fs_data

    def validate_profiles_interactive(self) -> None:
        """Interactive validation loop."""
        profiles = self.identify_profiles_to_validate()

        console.print(f"\n[bold]Profiles to validate: {len(profiles)}[/bold]\n")

        # Show summary table
        table = Table(title="Profiles Needing Validation")
        table.add_column("#", style="cyan")
        table.add_column("WikiTree ID", style="green")
        table.add_column("Name", style="yellow")
        table.add_column("Birth Year", style="magenta")

        for i, profile in enumerate(profiles, 1):
            birth_year = profile['birth_date'].split('-')[0] if profile['birth_date'] else "Unknown"
            table.add_row(str(i), profile['wikitree_id'], profile['name'], birth_year)

        console.print(table)
        console.print()

        # Ask how many to validate now
        start_idx = 0
        batch_size = len(profiles)

        if len(profiles) > 5:
            do_batch = Confirm.ask(f"Validate all {len(profiles)} profiles now?", default=False)
            if not do_batch:
                batch_size = int(Prompt.ask("How many profiles to validate in this session?", default="5"))
                start_from = Prompt.ask("Start from profile number?", default="1")
                start_idx = int(start_from) - 1

        # Process profiles
        validated_count = 0
        for i in range(start_idx, min(start_idx + batch_size, len(profiles))):
            profile = profiles[i]

            self.show_profile_info(profile)

            # Offer to open URL
            if Confirm.ask("Open FamilySearch URL in browser?", default=True):
                import webbrowser
                webbrowser.open(profile['search_url'])
                console.print("[yellow]Opened in browser. Search for the record and come back here.[/yellow]\n")

            fs_data = self.enter_familysearch_data(profile)

            if fs_data.get("validation_status") != "no_record_found":
                # Add to extracted data
                if "data" not in self.extracted_data:
                    self.extracted_data["data"] = {}

                self.extracted_data["data"][profile['wikitree_id']] = fs_data
                validated_count += 1

                console.print(f"[green]✓[/green] Validation added for {profile['wikitree_id']}\n")

            # Save progress after each entry
            self.save_extracted_data()

            # Ask if continue
            if i < min(start_idx + batch_size, len(profiles)) - 1:
                if not Confirm.ask("Continue to next profile?", default=True):
                    break

        console.print(f"\n[bold green]✓ Session complete![/bold green]")
        console.print(f"Validated in this session: {validated_count}")
        console.print(f"Total validated: {len(self.extracted_data.get('data', {}))}")

    def save_extracted_data(self) -> None:
        """Save extracted data to file."""
        self.extracted_data["generated_at"] = datetime.now().isoformat()
        self.extracted_data["extraction_type"] = "familysearch_mixed_extraction"
        self.extracted_data["people_searched"] = len(self.extracted_data.get("data", {}))

        with open(self.extracted_data_file, "w") as f:
            json.dump(self.extracted_data, f, indent=2, default=str)

        console.print(f"[dim]Saved to {self.extracted_data_file}[/dim]")


def main():
    """Main execution."""
    extracted_data_file = Path("familysearch_extracted_data.json")
    validation_results_file = Path("ancestry_validation_results.json")

    if not validation_results_file.exists():
        console.print(f"[red]Error: {validation_results_file} not found[/red]")
        return

    console.print("[bold cyan]═══ FamilySearch Validation Data Entry ═══[/bold cyan]\n")

    entry = FamilySearchDataEntry(extracted_data_file, validation_results_file)
    entry.load_existing_data()

    profiles_needed = entry.identify_profiles_to_validate()
    console.print(f"Profiles needing validation: {len(profiles_needed)}")
    console.print(f"Already validated: {len(entry.extracted_data.get('data', {}))}\n")

    if len(profiles_needed) == 0:
        console.print("[green]✓ All profiles already validated![/green]")
        return

    entry.validate_profiles_interactive()


if __name__ == "__main__":
    main()
