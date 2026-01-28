#!/usr/bin/env python3
"""
Stealthy Census & Primary Source Validator
Human-like pacing with proper rate limiting and caching
"""

import asyncio
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set
from playwright.async_api import async_playwright, Page, BrowserContext
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class StealthyCensusValidator:
    """Validates against census with human-like behavior and aggressive caching"""

    def __init__(self, tree_file: str = "expanded_tree.json"):
        self.tree_file = Path(tree_file)
        self.profiles: Dict = {}
        self.validations: Dict = {}
        self.progress_file = Path("census_validation_progress.json")
        self.data_file = Path("census_primary_data.json")
        self.cache_file = Path("census_fetch_cache.json")

        # Load cache
        self.fetch_cache: Dict = {}
        if self.cache_file.exists():
            with open(self.cache_file) as f:
                self.fetch_cache = json.load(f)

        # Track what's been processed
        self.processed_ids: Set[str] = set()

        # Browser automation
        self.playwright = None
        self.browser: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # Rate limiting configuration
        self.min_delay = 5.0  # Minimum 5 seconds between pages
        self.max_delay = 15.0  # Maximum 15 seconds between pages
        self.break_every = 15  # Take a break after this many profiles
        self.break_duration = (45, 90)  # Break for 45-90 seconds
        self.consecutive_errors = 0
        self.max_consecutive_errors = 3

        # Statistics
        self.stats = {
            "total_profiles": 0,
            "census_found": 0,
            "birth_records": 0,
            "death_records": 0,
            "marriage_records": 0,
            "immigration_records": 0,
            "military_records": 0,
            "other_records": 0,
            "not_found": 0,
            "rate_limited": 0,
            "cache_hits": 0,
        }

        self.profiles_processed = 0

    def load_data(self):
        """Load tree and existing validations"""
        console.print("\n[cyan]Loading data...[/cyan]")

        # Load tree
        with open(self.tree_file) as f:
            tree_data = json.load(f)
            self.profiles = tree_data.get("people", {})

        console.print(f"  Loaded {len(self.profiles)} profiles")

        # Load existing validations
        if self.data_file.exists():
            with open(self.data_file) as f:
                self.validations = json.load(f)
            console.print(f"  Loaded {len(self.validations)} existing validations")

        # Load progress
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                progress = json.load(f)
                self.processed_ids = set(progress.get("processed_ids", []))
                self.stats = progress.get("stats", self.stats)
            console.print(f"  Resumed: {len(self.processed_ids)} already processed")

        console.print(f"  Cache contains {len(self.fetch_cache)} cached fetches")

    async def initialize_browser(self) -> bool:
        """Initialize browser with FamilySearch profile"""
        console.print("\n[cyan]Initializing browser...[/cyan]")

        try:
            self.playwright = await async_playwright().start()

            # Use Chrome with persistent context (maintains login)
            fs_profile = Path.home() / ".familysearch_chrome_profile"
            fs_profile.mkdir(exist_ok=True)

            self.browser = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(fs_profile),
                headless=False,
                channel="chrome",
                viewport={"width": 1400, "height": 900},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox"
                ]
            )

            self.page = self.browser.pages[0] if self.browser.pages else await self.browser.new_page()
            await self.page.bring_to_front()

            console.print("[green]✓[/green] Browser initialized\n")
            return True

        except Exception as e:
            console.print(f"[red]✗[/red] Browser initialization failed: {e}", markup=False)
            return False

    async def check_login(self) -> bool:
        """Check if already logged into FamilySearch"""
        console.print("[cyan]Checking FamilySearch login...[/cyan]")

        try:
            await self.page.goto("https://www.familysearch.org", timeout=60000)
            await self.human_delay(2, 4)

            # Check if already logged in
            try:
                await self.page.wait_for_selector("text=Family Tree", timeout=3000)
                console.print("[green]✓[/green] Already logged in!")
                return True
            except:
                console.print("[yellow]Not logged in. Please log in manually in the browser.[/yellow]")
                console.print("Waiting for login... (checking every 10 seconds)")

                # Wait for login
                max_wait = 300
                waited = 0
                while waited < max_wait:
                    try:
                        await self.page.wait_for_selector("text=Family Tree", timeout=1000)
                        console.print("[green]✓[/green] Login detected!")
                        return True
                    except:
                        waited += 10
                        await asyncio.sleep(10)
                        console.print(f"[dim]Still waiting... ({waited}s / {max_wait}s)[/dim]")

                console.print("[yellow]Login timeout.[/yellow]")
                return False

        except Exception as e:
            console.print(f"[red]Error checking login: {e}[/red]", markup=False)
            return False

    async def human_delay(self, min_seconds: float = None, max_seconds: float = None):
        """Add human-like delay with jitter"""
        if min_seconds is None:
            min_seconds = self.min_delay
        if max_seconds is None:
            max_seconds = self.max_delay

        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    async def take_break(self):
        """Take a longer break to appear human"""
        break_time = random.uniform(*self.break_duration)
        console.print(f"\n[yellow]Taking a break for {int(break_time)} seconds...[/yellow]")
        await asyncio.sleep(break_time)
        console.print("[green]Resuming...[/green]\n")

    def get_cache_key(self, person_id: str, search_type: str) -> str:
        """Generate cache key for a search"""
        return f"{person_id}:{search_type}"

    def check_cache(self, person_id: str, search_type: str) -> Optional[List]:
        """Check if we've already fetched this data"""
        cache_key = self.get_cache_key(person_id, search_type)
        if cache_key in self.fetch_cache:
            self.stats["cache_hits"] += 1
            return self.fetch_cache[cache_key]
        return None

    def save_to_cache(self, person_id: str, search_type: str, data: List):
        """Save fetched data to cache"""
        cache_key = self.get_cache_key(person_id, search_type)
        self.fetch_cache[cache_key] = data

        # Save cache file
        with open(self.cache_file, 'w') as f:
            json.dump(self.fetch_cache, f, indent=2)

    async def handle_rate_limit(self, error_msg: str = "") -> bool:
        """Handle rate limiting with exponential backoff"""
        self.consecutive_errors += 1
        self.stats["rate_limited"] += 1

        if self.consecutive_errors >= self.max_consecutive_errors:
            console.print(f"\n[red]Rate limited {self.consecutive_errors} times. Stopping to avoid detection.[/red]")
            return False

        # Exponential backoff: 30s, 60s, 120s
        backoff_time = 30 * (2 ** (self.consecutive_errors - 1))
        console.print(f"\n[yellow]Rate limit detected. Backing off for {backoff_time} seconds...[/yellow]")
        if error_msg:
            console.print(f"[dim]{error_msg}[/dim]", markup=False)

        await asyncio.sleep(backoff_time)
        return True

    async def search_census_records(self, person_id: str, person_data: dict) -> List[Dict]:
        """Search for US Census records with caching"""

        # Check cache first
        cached = self.check_cache(person_id, "census")
        if cached is not None:
            console.print(f"[dim]  Using cached census data ({len(cached)} records)[/dim]")
            return cached

        census_records = []
        name = f"{person_data.get('first_name', '')} {person_data.get('last_name', '')}".strip()
        birth_year = person_data.get('birth_date', '')[:4] if person_data.get('birth_date') else ""

        if not name:
            self.save_to_cache(person_id, "census", census_records)
            return census_records

        try:
            # Navigate to Records search (with human delay)
            await self.page.goto("https://www.familysearch.org/en/search/record/results", timeout=60000)
            await self.human_delay(3, 6)

            # Check for rate limit indicators
            page_content = await self.page.content()
            if "429" in self.page.url or "rate limit" in page_content.lower():
                if not await self.handle_rate_limit("Census search page blocked"):
                    raise Exception("Rate limit exceeded")
                return census_records

            # Simple search without collection filtering
            try:
                await self.page.fill('input[name="givenName"]', person_data.get('first_name', ''), timeout=10000)
                await self.human_delay(0.5, 1.5)

                await self.page.fill('input[name="surname"]', person_data.get('last_name', ''), timeout=10000)
                await self.human_delay(0.5, 1.5)

                if birth_year:
                    await self.page.fill('input[name="birthLikeYear"]', birth_year, timeout=10000)
                    await self.human_delay(0.5, 1.5)

                # Search
                search_button = await self.page.wait_for_selector('button[type="submit"]', timeout=5000)
                await search_button.click()
                await self.human_delay(4, 8)  # Wait for results to load

                # Check for rate limit after search
                page_content = await self.page.content()
                if "429" in self.page.url or "rate limit" in page_content.lower():
                    if not await self.handle_rate_limit("Search results blocked"):
                        raise Exception("Rate limit exceeded")
                    return census_records

                # Get census results (look for census in title/description)
                result_links = await self.page.query_selector_all('a[href*="/ark:/61903/"]')
                console.print(f"[dim]  Found {len(result_links)} total results[/dim]")

                # Process up to 10 results that look like census
                census_count = 0
                for i, link in enumerate(result_links[:20]):  # Check first 20
                    if census_count >= 10:  # Stop after 10 census records
                        break

                    try:
                        # Get parent text to check if it's census
                        parent = await link.query_selector('..')
                        parent_text = await parent.text_content()

                        if "Census" not in parent_text:
                            continue

                        census_count += 1

                        # Click through to record
                        await link.click()
                        await self.human_delay(3, 6)  # Human delay after click

                        # Check for rate limit
                        if "429" in self.page.url:
                            if not await self.handle_rate_limit("Record page blocked"):
                                raise Exception("Rate limit exceeded")
                            break

                        # Extract census data
                        census_data = await self.extract_census_data()

                        if census_data:
                            census_records.append(census_data)
                            year = census_data.get('year', 'Unknown')
                            console.print(f"[green]  ✓[/green] Found census: {year}")
                            self.consecutive_errors = 0  # Reset on success

                        # Go back to results
                        await self.page.go_back()
                        await self.human_delay(2, 4)

                    except Exception as e:
                        error_str = str(e)
                        if "429" in error_str or "403" in error_str:
                            if not await self.handle_rate_limit(f"Error on record {i+1}"):
                                break
                        console.print(f"[dim]  Error extracting census {i+1}: {e}[/dim]", markup=False)
                        continue

            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "403" in error_str or "rate limit" in error_str.lower():
                    await self.handle_rate_limit("Census form error")
                else:
                    console.print(f"[dim]  Census form error: {e}[/dim]", markup=False)

        except Exception as e:
            error_str = str(e)
            if "Rate limit exceeded" in error_str:
                raise  # Propagate to stop validation
            console.print(f"[dim]  Census search error: {e}[/dim]", markup=False)

        # Save to cache
        self.save_to_cache(person_id, "census", census_records)
        return census_records

    async def extract_census_data(self) -> Optional[Dict]:
        """Extract ALL data from a census record page"""
        try:
            census_data = {
                "record_type": "US Census",
                "url": self.page.url,
                "extracted_at": datetime.now().isoformat(),
                "fields": {},
                "household": [],
            }

            # Get census year from title
            try:
                title = await self.page.text_content("h1", timeout=5000)
                census_data["title"] = title

                # Extract year
                import re
                year_match = re.search(r'(17|18|19|20)\d{2}', title)
                if year_match:
                    census_data["year"] = year_match.group(0)
            except:
                pass

            # Extract all field data
            field_rows = await self.page.query_selector_all('tr, .field-row, [class*="field"]')

            for row in field_rows[:50]:  # Limit to first 50 fields
                try:
                    text = await row.text_content()
                    if not text or len(text.strip()) < 3:
                        continue

                    parts = text.split(":", 1)
                    if len(parts) == 2:
                        field_name = parts[0].strip()
                        field_value = parts[1].strip()
                        census_data["fields"][field_name] = field_value
                except:
                    continue

            # Try to extract household table
            try:
                household_table = await self.page.query_selector('table')
                if household_table:
                    rows = await household_table.query_selector_all('tr')

                    for row in rows[1:11]:  # Skip header, limit to 10 members
                        cells = await row.query_selector_all('td, th')
                        if cells:
                            household_member = {}
                            for i, cell in enumerate(cells[:10]):  # First 10 columns
                                cell_text = await cell.text_content()
                                household_member[f"column_{i}"] = cell_text.strip()
                            census_data["household"].append(household_member)
            except:
                pass

            # Only return if we got meaningful data
            if census_data["fields"] or census_data["household"]:
                return census_data

            return None

        except Exception as e:
            console.print(f"[dim]  Error extracting census data: {e}[/dim]", markup=False)
            return None

    async def search_other_records(self, person_id: str, person_data: dict) -> List[Dict]:
        """Search for other primary sources with caching"""

        # Check cache first
        cached = self.check_cache(person_id, "other")
        if cached is not None:
            console.print(f"[dim]  Using cached other records ({len(cached)} records)[/dim]")
            return cached

        other_records = []
        name = f"{person_data.get('first_name', '')} {person_data.get('last_name', '')}".strip()

        if not name:
            self.save_to_cache(person_id, "other", other_records)
            return other_records

        try:
            # Navigate to all records search
            await self.page.goto("https://www.familysearch.org/en/search/record/results", timeout=60000)
            await self.human_delay(3, 6)

            # Check for rate limit
            page_content = await self.page.content()
            if "429" in self.page.url or "rate limit" in page_content.lower():
                if not await self.handle_rate_limit("Other records page blocked"):
                    raise Exception("Rate limit exceeded")
                return other_records

            # Simple search
            try:
                await self.page.fill('input[name="givenName"]', person_data.get('first_name', ''), timeout=10000)
                await self.human_delay(0.5, 1.5)

                await self.page.fill('input[name="surname"]', person_data.get('last_name', ''), timeout=10000)
                await self.human_delay(0.5, 1.5)

                # Search
                search_button = await self.page.wait_for_selector('button[type="submit"]', timeout=5000)
                await search_button.click()
                await self.human_delay(4, 8)

                # Check for rate limit
                if "429" in self.page.url:
                    if not await self.handle_rate_limit("Search results blocked"):
                        raise Exception("Rate limit exceeded")
                    return other_records

                # Get non-census results (up to 5)
                result_links = await self.page.query_selector_all('a[href*="/ark:/61903/"]')

                non_census_count = 0
                for i, link in enumerate(result_links[:15]):  # Check first 15
                    if non_census_count >= 5:  # Stop after 5 non-census records
                        break

                    try:
                        # Get result type
                        parent = await link.query_selector('..')
                        parent_text = await parent.text_content()

                        # Skip census (we already got those)
                        if "Census" in parent_text:
                            continue

                        non_census_count += 1

                        # Click through
                        await link.click()
                        await self.human_delay(3, 6)

                        # Check for rate limit
                        if "429" in self.page.url:
                            if not await self.handle_rate_limit("Record page blocked"):
                                break

                        # Extract record data
                        record_data = await self.extract_record_data()

                        if record_data:
                            other_records.append(record_data)
                            record_type = record_data.get("record_type", "Unknown")
                            console.print(f"[green]  ✓[/green] Found: {record_type}")
                            self.consecutive_errors = 0  # Reset on success

                        # Go back
                        await self.page.go_back()
                        await self.human_delay(2, 4)

                    except Exception as e:
                        error_str = str(e)
                        if "429" in error_str or "403" in error_str:
                            if not await self.handle_rate_limit(f"Error on record {i+1}"):
                                break
                        console.print(f"[dim]  Error extracting record {i+1}: {e}[/dim]", markup=False)
                        continue

            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "403" in error_str or "rate limit" in error_str.lower():
                    await self.handle_rate_limit("Other records form error")
                else:
                    console.print(f"[dim]  Other records form error: {e}[/dim]", markup=False)

        except Exception as e:
            error_str = str(e)
            if "Rate limit exceeded" in error_str:
                raise  # Propagate to stop validation
            console.print(f"[dim]  Other records search error: {e}[/dim]", markup=False)

        # Save to cache
        self.save_to_cache(person_id, "other", other_records)
        return other_records

    async def extract_record_data(self) -> Optional[Dict]:
        """Extract data from any record type"""
        try:
            record_data = {
                "url": self.page.url,
                "extracted_at": datetime.now().isoformat(),
                "fields": {},
            }

            # Get title to determine record type
            try:
                title = await self.page.text_content("h1", timeout=5000)
                record_data["title"] = title

                # Determine record type
                if "Birth" in title:
                    record_data["record_type"] = "Birth"
                elif "Death" in title or "Burial" in title:
                    record_data["record_type"] = "Death"
                elif "Marriage" in title:
                    record_data["record_type"] = "Marriage"
                elif "Immigration" in title or "Passenger" in title:
                    record_data["record_type"] = "Immigration"
                elif "Military" in title or "Draft" in title:
                    record_data["record_type"] = "Military"
                else:
                    record_data["record_type"] = "Other"
            except:
                record_data["record_type"] = "Unknown"

            # Extract all fields
            field_rows = await self.page.query_selector_all('tr, .field-row, [class*="field"]')

            for row in field_rows[:50]:  # Limit to first 50 fields
                try:
                    text = await row.text_content()
                    if not text or len(text.strip()) < 3:
                        continue

                    parts = text.split(":", 1)
                    if len(parts) == 2:
                        field_name = parts[0].strip()
                        field_value = parts[1].strip()
                        record_data["fields"][field_name] = field_value
                except:
                    continue

            if record_data["fields"]:
                return record_data

            return None

        except Exception as e:
            console.print(f"[dim]  Error extracting record: {e}[/dim]", markup=False)
            return None

    async def validate_profile(self, person_id: str, person_data: dict) -> Dict:
        """Validate a single profile against all primary sources"""

        name = f"{person_data.get('first_name', '')} {person_data.get('last_name', '')}".strip()
        birth_year = person_data.get('birth_date', '')[:4] if person_data.get('birth_date') else ""

        console.print(f"\n[cyan]Validating:[/cyan] {name} (b. {birth_year})")

        validation = {
            "person_id": person_id,
            "name": name,
            "birth_date": person_data.get('birth_date', ''),
            "validated_at": datetime.now().isoformat(),
            "census_records": [],
            "other_records": [],
            "summary": {}
        }

        try:
            # Search census records
            console.print("[dim]  Searching US Census...[/dim]")
            census_records = await self.search_census_records(person_id, person_data)
            validation["census_records"] = census_records
            self.stats["census_found"] += len(census_records)

            # Human delay between searches
            await self.human_delay(2, 5)

            # Search other records
            console.print("[dim]  Searching other primary sources...[/dim]")
            other_records = await self.search_other_records(person_id, person_data)
            validation["other_records"] = other_records

            # Count record types
            for record in other_records:
                record_type = record.get("record_type", "Other")
                if record_type == "Birth":
                    self.stats["birth_records"] += 1
                elif record_type == "Death":
                    self.stats["death_records"] += 1
                elif record_type == "Marriage":
                    self.stats["marriage_records"] += 1
                elif record_type == "Immigration":
                    self.stats["immigration_records"] += 1
                elif record_type == "Military":
                    self.stats["military_records"] += 1
                else:
                    self.stats["other_records"] += 1

            # Summary
            validation["summary"] = {
                "total_records": len(census_records) + len(other_records),
                "census_records": len(census_records),
                "other_records": len(other_records)
            }

            if validation["summary"]["total_records"] == 0:
                self.stats["not_found"] += 1
                console.print("[yellow]  No primary sources found[/yellow]")
            else:
                console.print(f"[green]✓[/green] Found {validation['summary']['total_records']} primary sources")

        except Exception as e:
            if "Rate limit exceeded" in str(e):
                raise  # Propagate to stop validation
            console.print(f"[red]  Error validating profile: {e}[/red]", markup=False)

        return validation

    async def validate_profiles(self, max_profiles: int = 150):
        """Validate profiles with human-like pacing"""

        # Filter to profiles not yet processed
        to_validate = [
            (pid, pdata) for pid, pdata in self.profiles.items()
            if pid not in self.processed_ids
        ][:max_profiles]

        console.print(f"\n[cyan]Validating up to {max_profiles} profiles...[/cyan]")
        console.print(f"Total to validate: {len(to_validate)}\n")
        console.print("[yellow]Using human-like pacing with 5-15 second delays[/yellow]")
        console.print("[yellow]Taking breaks every 15 profiles[/yellow]\n")

        try:
            for i, (person_id, person_data) in enumerate(to_validate):
                self.profiles_processed += 1

                try:
                    # Validate
                    validation = await self.validate_profile(person_id, person_data)

                    # Save
                    self.validations[person_id] = validation
                    self.processed_ids.add(person_id)

                    # Save progress after each profile
                    self.save_progress()
                    self.save_validations()

                    # Take a break periodically
                    if (i + 1) % self.break_every == 0:
                        await self.take_break()
                    else:
                        # Regular human delay between profiles
                        await self.human_delay()

                except Exception as e:
                    if "Rate limit exceeded" in str(e):
                        console.print("\n[red]Stopping due to repeated rate limits.[/red]")
                        break
                    console.print(f"[red]Error validating {person_id}: {e}[/red]", markup=False)
                    continue

        except Exception as e:
            console.print(f"\n[red]Validation error: {e}[/red]", markup=False)

        console.print("\n[green]✓[/green] Validation complete (or paused)!")
        self.print_final_report()

    def save_progress(self):
        """Save progress checkpoint"""
        progress = {
            "last_updated": datetime.now().isoformat(),
            "processed_ids": list(self.processed_ids),
            "stats": self.stats
        }

        with open(self.progress_file, 'w') as f:
            json.dump(progress, f, indent=2)

    def save_validations(self):
        """Save all validation data"""
        with open(self.data_file, 'w') as f:
            json.dump(self.validations, f, indent=2)

    def print_final_report(self):
        """Print final validation statistics"""
        console.print("\n[bold cyan]═══ CENSUS & PRIMARY SOURCE VALIDATION REPORT ═══[/bold cyan]\n")

        from rich.table import Table

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="green")

        table.add_row("Total Profiles Processed", str(len(self.processed_ids)))
        table.add_row("US Census Records", str(self.stats["census_found"]))
        table.add_row("Birth Records", str(self.stats["birth_records"]))
        table.add_row("Death Records", str(self.stats["death_records"]))
        table.add_row("Marriage Records", str(self.stats["marriage_records"]))
        table.add_row("Immigration Records", str(self.stats["immigration_records"]))
        table.add_row("Military Records", str(self.stats["military_records"]))
        table.add_row("Other Records", str(self.stats["other_records"]))
        table.add_row("Not Found", str(self.stats["not_found"]))
        table.add_row("", "")
        table.add_row("Cache Hits", str(self.stats["cache_hits"]))
        table.add_row("Rate Limited", str(self.stats["rate_limited"]))

        console.print(table)

        total_records = (
            self.stats["census_found"] +
            self.stats["birth_records"] +
            self.stats["death_records"] +
            self.stats["marriage_records"] +
            self.stats["immigration_records"] +
            self.stats["military_records"] +
            self.stats["other_records"]
        )

        console.print(f"\n[bold]Total Primary Sources Found: {total_records}[/bold]")
        console.print(f"[bold]Data saved to: {self.data_file}[/bold]")
        console.print(f"[bold]Cache saved to: {self.cache_file}[/bold]\n")

    async def run(self):
        """Main execution"""
        try:
            # Load data
            self.load_data()

            # Initialize browser
            if not await self.initialize_browser():
                return

            # Check login
            if not await self.check_login():
                console.print("\n[red]Not logged in. Please log in and try again.[/red]\n")
                return

            console.print("[green]✓[/green] Ready to validate!\n")

            console.print(f"{len(self.profiles)} profiles will be validated against:")
            console.print("  • US Census (all years)")
            console.print("  • Birth records")
            console.print("  • Death records")
            console.print("  • Marriage records")
            console.print("  • Immigration records")
            console.print("  • Military records")
            console.print("  • Other primary sources\n")

            # Validate
            await self.validate_profiles(max_profiles=150)

        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]", markup=False)

        finally:
            # Cleanup
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()


async def main():
    validator = StealthyCensusValidator()
    await validator.run()


if __name__ == "__main__":
    asyncio.run(main())
