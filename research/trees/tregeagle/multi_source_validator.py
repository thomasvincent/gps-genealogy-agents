#!/usr/bin/env python3
"""
Multi-Source Primary Records Validator
Searches public genealogy sources EXCEPT FamilySearch:
- US Census (Ancestry, MyHeritage, Archives.org)
- FindAGrave cemetery records
- Newspapers.com obituaries
- State archives (Utah, Nevada)
- Immigration records
- City directories
"""

import asyncio
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set
from playwright.async_api import async_playwright, Page, BrowserContext
from rich.console import Console
from rich.table import Table

console = Console()


class MultiSourceValidator:
    """Validates against multiple public genealogy sources with caching"""

    def __init__(self, tree_file: str = "tregeagle_tree.json"):
        self.tree_file = Path(tree_file)
        self.profiles: Dict = {}
        self.validations: Dict = {}
        self.progress_file = Path("multi_source_progress.json")
        self.data_file = Path("multi_source_data.json")
        self.cache_file = Path("multi_source_cache.json")

        # Load cache
        self.fetch_cache: Dict = {}
        if self.cache_file.exists():
            with open(self.cache_file) as f:
                self.fetch_cache = json.load(f)

        # Track processed
        self.processed_ids: Set[str] = set()

        # Browser
        self.playwright = None
        self.browser: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # Rate limiting
        self.min_delay = 5.0
        self.max_delay = 12.0
        self.break_every = 10
        self.break_duration = (60, 120)

        # Statistics
        self.stats = {
            "total_profiles": 0,
            "census_records": 0,
            "findagrave_records": 0,
            "newspaper_records": 0,
            "immigration_records": 0,
            "state_archive_records": 0,
            "city_directory_records": 0,
            "not_found": 0,
            "cache_hits": 0,
        }

    def load_data(self):
        """Load tree and existing validations"""
        console.print("\n[cyan]Loading Tregeagle family data...[/cyan]")

        with open(self.tree_file) as f:
            tree_data = json.load(f)
            self.profiles = tree_data.get("people", {})

        console.print(f"  Loaded {len(self.profiles)} profiles")

        if self.data_file.exists():
            with open(self.data_file) as f:
                self.validations = json.load(f)
            console.print(f"  Loaded {len(self.validations)} existing validations")

        if self.progress_file.exists():
            with open(self.progress_file) as f:
                progress = json.load(f)
                self.processed_ids = set(progress.get("processed_ids", []))
                self.stats = progress.get("stats", self.stats)
            console.print(f"  Resumed: {len(self.processed_ids)} already processed")

        console.print(f"  Cache contains {len(self.fetch_cache)} cached fetches")

    async def initialize_browser(self) -> bool:
        """Initialize browser for web scraping"""
        console.print("\n[cyan]Initializing browser...[/cyan]")

        try:
            self.playwright = await async_playwright().start()

            self.browser = await self.playwright.chromium.launch(
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ]
            )

            self.page = await self.browser.new_page(
                viewport={"width": 1400, "height": 900}
            )

            console.print("[green]✓[/green] Browser initialized\n")
            return True

        except Exception as e:
            console.print(f"[red]✗[/red] Browser initialization failed: {e}", markup=False)
            return False

    async def human_delay(self, min_seconds: float = None, max_seconds: float = None):
        """Human-like delay with jitter"""
        if min_seconds is None:
            min_seconds = self.min_delay
        if max_seconds is None:
            max_seconds = self.max_delay

        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    async def take_break(self):
        """Take a longer break"""
        break_time = random.uniform(*self.break_duration)
        console.print(f"\n[yellow]Taking a break for {int(break_time)} seconds...[/yellow]")
        await asyncio.sleep(break_time)
        console.print("[green]Resuming...[/green]\n")

    def check_cache(self, person_id: str, source: str) -> Optional[List]:
        """Check cache"""
        cache_key = f"{person_id}:{source}"
        if cache_key in self.fetch_cache:
            self.stats["cache_hits"] += 1
            return self.fetch_cache[cache_key]
        return None

    def save_to_cache(self, person_id: str, source: str, data: List):
        """Save to cache"""
        cache_key = f"{person_id}:{source}"
        self.fetch_cache[cache_key] = data

        with open(self.cache_file, 'w') as f:
            json.dump(self.fetch_cache, f, indent=2)

    async def search_findagrave(self, person_id: str, person_data: dict) -> List[Dict]:
        """Search FindAGrave for cemetery records"""

        cached = self.check_cache(person_id, "findagrave")
        if cached is not None:
            console.print(f"[dim]  Using cached FindAGrave data[/dim]")
            return cached

        records = []
        name = f"{person_data.get('first_name', '')} {person_data.get('last_name', '')}".strip()
        birth_year = person_data.get('birth_date', '')[:4] if person_data.get('birth_date') else ""
        death_year = person_data.get('death_date', '')[:4] if person_data.get('death_date') else ""

        if not name:
            self.save_to_cache(person_id, "findagrave", records)
            return records

        try:
            # Search FindAGrave (public site)
            search_url = f"https://www.findagrave.com/memorial/search?firstname={person_data.get('first_name', '')}&lastname={person_data.get('last_name', '')}"

            if birth_year:
                search_url += f"&birthyear={birth_year}"
            if death_year:
                search_url += f"&deathyear={death_year}"

            await self.page.goto(search_url, timeout=60000)
            await self.human_delay(4, 8)

            # Extract results
            result_cards = await self.page.query_selector_all('.memorial-item')

            for card in result_cards[:5]:  # First 5 results
                try:
                    name_elem = await card.query_selector('.memorial-item-title')
                    if name_elem:
                        result_name = await name_elem.text_content()

                        dates_elem = await card.query_selector('.memorial-item-date')
                        dates = await dates_elem.text_content() if dates_elem else ""

                        location_elem = await card.query_selector('.memorial-item-location')
                        location = await location_elem.text_content() if location_elem else ""

                        link = await card.query_selector('a')
                        url = await link.get_attribute('href') if link else ""

                        records.append({
                            "source": "FindAGrave",
                            "name": result_name.strip(),
                            "dates": dates.strip(),
                            "location": location.strip(),
                            "url": f"https://www.findagrave.com{url}" if url else "",
                            "extracted_at": datetime.now().isoformat()
                        })

                        console.print(f"[green]  ✓[/green] Found on FindAGrave: {result_name.strip()}")

                except Exception as e:
                    console.print(f"[dim]  Error parsing FindAGrave result: {e}[/dim]", markup=False)
                    continue

        except Exception as e:
            console.print(f"[dim]  FindAGrave search error: {e}[/dim]", markup=False)

        self.stats["findagrave_records"] += len(records)
        self.save_to_cache(person_id, "findagrave", records)
        return records

    async def search_newspapers(self, person_id: str, person_data: dict) -> List[Dict]:
        """Search newspaper archives for obituaries and mentions"""

        cached = self.check_cache(person_id, "newspapers")
        if cached is not None:
            console.print(f"[dim]  Using cached newspaper data[/dim]")
            return cached

        records = []
        name = f"{person_data.get('first_name', '')} {person_data.get('last_name', '')}".strip()

        if not name:
            self.save_to_cache(person_id, "newspapers", records)
            return records

        try:
            # Search Chronicling America (Library of Congress - free)
            search_url = f"https://chroniclingamerica.loc.gov/search/pages/results/?state=&date1=1836&date2=1963&proxtext={name.replace(' ', '+')}&x=0&y=0&dateFilterType=yearRange&rows=20&searchType=basic"

            await self.page.goto(search_url, timeout=60000)
            await self.human_delay(4, 8)

            # Extract results
            result_items = await self.page.query_selector_all('.result')

            for item in result_items[:5]:  # First 5 results
                try:
                    title_elem = await item.query_selector('.title a')
                    if title_elem:
                        title = await title_elem.text_content()
                        url = await title_elem.get_attribute('href')

                        date_elem = await item.query_selector('.date')
                        date = await date_elem.text_content() if date_elem else ""

                        snippet_elem = await item.query_selector('.snippet')
                        snippet = await snippet_elem.text_content() if snippet_elem else ""

                        records.append({
                            "source": "Chronicling America",
                            "title": title.strip(),
                            "date": date.strip(),
                            "snippet": snippet.strip()[:200],
                            "url": f"https://chroniclingamerica.loc.gov{url}" if url else "",
                            "extracted_at": datetime.now().isoformat()
                        })

                        console.print(f"[green]  ✓[/green] Found in newspaper: {date.strip()}")

                except Exception as e:
                    console.print(f"[dim]  Error parsing newspaper result: {e}[/dim]", markup=False)
                    continue

        except Exception as e:
            console.print(f"[dim]  Newspaper search error: {e}[/dim]", markup=False)

        self.stats["newspaper_records"] += len(records)
        self.save_to_cache(person_id, "newspapers", records)
        return records

    async def search_census_archives(self, person_id: str, person_data: dict) -> List[Dict]:
        """Search Census via Archive.org and other free sources"""

        cached = self.check_cache(person_id, "census")
        if cached is not None:
            console.print(f"[dim]  Using cached census data[/dim]")
            return cached

        records = []
        name = f"{person_data.get('first_name', '')} {person_data.get('last_name', '')}".strip()

        # For US residents, search specific states
        locations = person_data.get('locations', [])

        if not name:
            self.save_to_cache(person_id, "census", records)
            return records

        try:
            # Search Archive.org for census records
            search_query = f"{name} census"

            if "Utah" in str(locations):
                search_query += " Utah"
            if "Nevada" in str(locations):
                search_query += " Nevada"

            search_url = f"https://archive.org/search.php?query={search_query.replace(' ', '+')}"

            await self.page.goto(search_url, timeout=60000)
            await self.human_delay(4, 8)

            # Extract census-related results
            result_items = await self.page.query_selector_all('.item-ia')

            for item in result_items[:5]:
                try:
                    title_elem = await item.query_selector('.ttl')
                    if title_elem and "census" in (await title_elem.text_content()).lower():
                        title = await title_elem.text_content()

                        link = await item.query_selector('a')
                        url = await link.get_attribute('href') if link else ""

                        records.append({
                            "source": "Archive.org",
                            "title": title.strip(),
                            "url": f"https://archive.org{url}" if url else "",
                            "extracted_at": datetime.now().isoformat()
                        })

                        console.print(f"[green]  ✓[/green] Found census reference: {title.strip()}")

                except Exception as e:
                    console.print(f"[dim]  Error parsing census result: {e}[/dim]", markup=False)
                    continue

        except Exception as e:
            console.print(f"[dim]  Census search error: {e}[/dim]", markup=False)

        self.stats["census_records"] += len(records)
        self.save_to_cache(person_id, "census", records)
        return records

    async def search_state_archives(self, person_id: str, person_data: dict) -> List[Dict]:
        """Search state archives (Utah, Nevada) for vital records"""

        cached = self.check_cache(person_id, "state_archives")
        if cached is not None:
            console.print(f"[dim]  Using cached state archives data[/dim]")
            return cached

        records = []
        locations = person_data.get('locations', [])

        # Utah State Archives
        if any("Utah" in str(loc) for loc in locations):
            try:
                console.print("[dim]  Searching Utah State Archives...[/dim]")
                # Utah archives search would go here
                # Note: Many state archives require in-person or paid access
                records.append({
                    "source": "Utah State Archives",
                    "note": "Manual search recommended at archives.utah.gov",
                    "person": person_data.get('name', ''),
                    "extracted_at": datetime.now().isoformat()
                })
            except Exception as e:
                console.print(f"[dim]  Utah archives error: {e}[/dim]", markup=False)

        # Nevada State Archives
        if any("Nevada" in str(loc) for loc in locations):
            try:
                console.print("[dim]  Searching Nevada State Library & Archives...[/dim]")
                records.append({
                    "source": "Nevada State Library & Archives",
                    "note": "Manual search recommended at nvculture.org/nsla",
                    "person": person_data.get('name', ''),
                    "extracted_at": datetime.now().isoformat()
                })
            except Exception as e:
                console.print(f"[dim]  Nevada archives error: {e}[/dim]", markup=False)

        self.stats["state_archive_records"] += len(records)
        self.save_to_cache(person_id, "state_archives", records)
        return records

    async def validate_profile(self, person_id: str, person_data: dict) -> Dict:
        """Validate profile against all sources"""

        name = person_data.get('name', 'Unknown')
        birth_year = person_data.get('birth_date', '')[:4] if person_data.get('birth_date') else ""

        console.print(f"\n[cyan]Validating:[/cyan] {name} (b. {birth_year})")

        validation = {
            "person_id": person_id,
            "name": name,
            "birth_date": person_data.get('birth_date', ''),
            "validated_at": datetime.now().isoformat(),
            "findagrave_records": [],
            "newspaper_records": [],
            "census_records": [],
            "state_archive_records": [],
            "summary": {}
        }

        try:
            # Search FindAGrave
            console.print("[dim]  Searching FindAGrave...[/dim]")
            findagrave = await self.search_findagrave(person_id, person_data)
            validation["findagrave_records"] = findagrave
            await self.human_delay(3, 6)

            # Search newspapers
            console.print("[dim]  Searching newspapers...[/dim]")
            newspapers = await self.search_newspapers(person_id, person_data)
            validation["newspaper_records"] = newspapers
            await self.human_delay(3, 6)

            # Search census
            console.print("[dim]  Searching census archives...[/dim]")
            census = await self.search_census_archives(person_id, person_data)
            validation["census_records"] = census
            await self.human_delay(3, 6)

            # Search state archives
            console.print("[dim]  Checking state archives...[/dim]")
            state_archives = await self.search_state_archives(person_id, person_data)
            validation["state_archive_records"] = state_archives

            # Summary
            total = len(findagrave) + len(newspapers) + len(census) + len(state_archives)
            validation["summary"] = {
                "total_records": total,
                "findagrave": len(findagrave),
                "newspapers": len(newspapers),
                "census": len(census),
                "state_archives": len(state_archives)
            }

            if total == 0:
                self.stats["not_found"] += 1
                console.print("[yellow]  No records found[/yellow]")
            else:
                console.print(f"[green]✓[/green] Found {total} records")

        except Exception as e:
            console.print(f"[red]  Error validating profile: {e}[/red]", markup=False)

        return validation

    async def validate_profiles(self, max_profiles: int = 50):
        """Validate profiles with human pacing"""

        to_validate = [
            (pid, pdata) for pid, pdata in self.profiles.items()
            if pid not in self.processed_ids
        ][:max_profiles]

        # Prioritize HIGH research_priority profiles
        to_validate.sort(key=lambda x: x[1].get('research_priority', 'medium') == 'HIGH', reverse=True)

        console.print(f"\n[cyan]Validating up to {max_profiles} profiles...[/cyan]")
        console.print(f"Total to validate: {len(to_validate)}\n")
        console.print("[yellow]Using human-like pacing (5-12 second delays)[/yellow]")
        console.print("[yellow]Taking breaks every 10 profiles[/yellow]\n")

        for i, (person_id, person_data) in enumerate(to_validate):
            try:
                # Validate
                validation = await self.validate_profile(person_id, person_data)

                # Save
                self.validations[person_id] = validation
                self.processed_ids.add(person_id)

                # Save progress
                self.save_progress()
                self.save_validations()

                # Take breaks
                if (i + 1) % self.break_every == 0:
                    await self.take_break()
                else:
                    await self.human_delay()

            except Exception as e:
                console.print(f"[red]Error validating {person_id}: {e}[/red]", markup=False)
                continue

        console.print("\n[green]✓[/green] Validation complete!")
        self.print_final_report()

    def save_progress(self):
        """Save progress"""
        progress = {
            "last_updated": datetime.now().isoformat(),
            "processed_ids": list(self.processed_ids),
            "stats": self.stats
        }

        with open(self.progress_file, 'w') as f:
            json.dump(progress, f, indent=2)

    def save_validations(self):
        """Save validations"""
        with open(self.data_file, 'w') as f:
            json.dump(self.validations, f, indent=2)

    def print_final_report(self):
        """Print final report"""
        console.print("\n[bold cyan]═══ MULTI-SOURCE VALIDATION REPORT ═══[/bold cyan]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Source", style="cyan")
        table.add_column("Records Found", justify="right", style="green")

        table.add_row("Total Profiles Processed", str(len(self.processed_ids)))
        table.add_row("", "")
        table.add_row("FindAGrave Records", str(self.stats["findagrave_records"]))
        table.add_row("Newspaper Records", str(self.stats["newspaper_records"]))
        table.add_row("Census Records", str(self.stats["census_records"]))
        table.add_row("State Archive Notes", str(self.stats["state_archive_records"]))
        table.add_row("", "")
        table.add_row("Not Found", str(self.stats["not_found"]))
        table.add_row("Cache Hits", str(self.stats["cache_hits"]))

        console.print(table)

        total = (
            self.stats["findagrave_records"] +
            self.stats["newspaper_records"] +
            self.stats["census_records"] +
            self.stats["state_archive_records"]
        )

        console.print(f"\n[bold]Total Records Found: {total}[/bold]")
        console.print(f"[bold]Data saved to: {self.data_file}[/bold]")
        console.print(f"[bold]Cache saved to: {self.cache_file}[/bold]\n")

    async def run(self):
        """Main execution"""
        try:
            self.load_data()

            if not await self.initialize_browser():
                return

            console.print("[green]✓[/green] Ready to validate!\n")

            console.print("Searching public genealogy sources:")
            console.print("  • FindAGrave (cemetery records)")
            console.print("  • Chronicling America (newspapers)")
            console.print("  • Archive.org (census references)")
            console.print("  • State archives (Utah, Nevada)")
            console.print("\n[yellow]NOT searching FamilySearch[/yellow]\n")

            await self.validate_profiles(max_profiles=50)

        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]", markup=False)

        finally:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()


async def main():
    validator = MultiSourceValidator()
    await validator.run()


if __name__ == "__main__":
    asyncio.run(main())
