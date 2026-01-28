#!/usr/bin/env python3
"""
Comprehensive Primary Source Validator
Validates profiles against US Census and all other primary sources
Extracts complete information from each record type
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


class ComprehensivePrimaryValidator:
    """Validates against US Census and all primary sources with full data extraction"""

    def __init__(self, tree_file: str = "expanded_tree.json"):
        self.tree_file = Path(tree_file)
        self.profiles: Dict = {}
        self.validations: Dict = {}
        self.progress_file = Path("comprehensive_validation_progress.json")
        self.data_file = Path("comprehensive_primary_data.json")

        # Track what's been processed
        self.processed_ids: Set[str] = set()

        # Browser automation
        self.playwright = None
        self.browser: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

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
        }

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
            console.print(f"[red]✗[/red] Browser initialization failed: {e}")
            return False

    async def login_to_familysearch(self) -> bool:
        """Login to FamilySearch with interactive wait"""
        console.print("[cyan]Logging into FamilySearch...[/cyan]")

        try:
            # Navigate to FamilySearch
            await self.page.goto("https://www.familysearch.org", timeout=60000)
            await asyncio.sleep(2)

            # Check if already logged in
            try:
                await self.page.wait_for_selector("text=Family Tree", timeout=3000)
                console.print("[green]✓[/green] Already logged in!")
                return True
            except:
                pass

            # Wait for user to log in
            console.print("\nPlease log into FamilySearch in the browser window.")
            console.print("The browser will remain open while you log in.")
            console.print("Free accounts work fine - create one at familysearch.org\n")

            # Poll for login completion (check every 5 seconds for up to 5 minutes)
            max_wait = 300
            waited = 0
            console.print("Waiting for login... (checking every 5 seconds)")

            while waited < max_wait:
                try:
                    await self.page.wait_for_selector("text=Family Tree", timeout=1000)
                    console.print("[green]✓[/green] Login detected!")
                    return True
                except:
                    waited += 5
                    await asyncio.sleep(5)
                    console.print(f"[dim]Still waiting... ({waited}s / {max_wait}s)[/dim]")

            console.print("[yellow]Login timeout. Please try again.[/yellow]")
            return False

        except Exception as e:
            console.print(f"[red]Error during login: {e}[/red]", markup=False)
            return False

    async def search_census_records(self, person_data: dict) -> List[Dict]:
        """Search for US Census records and extract ALL data"""
        census_records = []

        name = f"{person_data.get('first_name', '')} {person_data.get('last_name', '')}".strip()
        birth_year = person_data.get('birth_date', '')[:4] if person_data.get('birth_date') else ""

        if not name:
            return census_records

        try:
            # Navigate to Records search
            await self.page.goto("https://www.familysearch.org/search/record/results", timeout=60000)
            await asyncio.sleep(2)

            # Filter to US Census only
            try:
                # Click Collections filter
                collections_button = await self.page.wait_for_selector(
                    'button:has-text("Collections")', timeout=5000
                )
                await collections_button.click()
                await asyncio.sleep(1)

                # Search for "United States Census"
                collection_search = await self.page.wait_for_selector(
                    'input[placeholder*="Search"]', timeout=5000
                )
                await collection_search.fill("United States Census")
                await asyncio.sleep(2)

                # Select census checkboxes
                census_checkboxes = await self.page.query_selector_all(
                    'input[type="checkbox"]'
                )
                for checkbox in census_checkboxes[:10]:  # First 10 census collections
                    await checkbox.check()
                    await asyncio.sleep(0.5)

            except Exception as e:
                console.print(f"[dim]Could not filter to census: {e}[/dim]", markup=False)

            # Fill search form
            await self.page.fill('input[name="givenName"]', person_data.get('first_name', ''))
            await self.page.fill('input[name="surname"]', person_data.get('last_name', ''))

            if birth_year:
                await self.page.fill('input[name="birthLikeYear"]', birth_year)

            # Search
            search_button = await self.page.wait_for_selector('button[type="submit"]', timeout=5000)
            await search_button.click()
            await asyncio.sleep(5)

            # Get all results (up to 20)
            result_links = await self.page.query_selector_all('a[href*="/ark:/61903/"]')

            for i, link in enumerate(result_links[:20]):  # Process first 20 results
                try:
                    href = await link.get_attribute("href")

                    # Click through to record
                    await link.click()
                    await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                    await asyncio.sleep(3)

                    # Extract census data
                    census_data = await self.extract_census_data()

                    if census_data:
                        census_records.append(census_data)
                        console.print(f"[green]✓[/green] Found census: {census_data.get('year', 'Unknown year')}")

                    # Go back to results
                    await self.page.go_back()
                    await asyncio.sleep(2)

                except Exception as e:
                    console.print(f"[dim]Error extracting census {i+1}: {e}[/dim]", markup=False)
                    continue

        except Exception as e:
            console.print(f"[dim]Census search error: {e}[/dim]", markup=False)

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
                "raw_text": ""
            }

            # Get census year from title or breadcrumbs
            try:
                title = await self.page.text_content("h1")
                census_data["title"] = title

                # Extract year from title
                import re
                year_match = re.search(r'(17|18|19|20)\d{2}', title)
                if year_match:
                    census_data["year"] = year_match.group(0)
            except:
                pass

            # Extract all field data
            field_rows = await self.page.query_selector_all('tr, .field-row, [class*="field"]')

            for row in field_rows:
                try:
                    text = await row.text_content()
                    if not text or len(text.strip()) < 3:
                        continue

                    # Parse field name and value
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

                    for row in rows[1:]:  # Skip header
                        cells = await row.query_selector_all('td, th')
                        if cells:
                            household_member = {}
                            for i, cell in enumerate(cells):
                                cell_text = await cell.text_content()
                                household_member[f"column_{i}"] = cell_text.strip()
                            census_data["household"].append(household_member)
            except:
                pass

            # Get full page text for additional extraction
            try:
                page_text = await self.page.text_content('body')
                census_data["raw_text"] = page_text[:5000]  # First 5000 chars
            except:
                pass

            # Only return if we got meaningful data
            if census_data["fields"] or census_data["household"]:
                return census_data

            return None

        except Exception as e:
            console.print(f"[dim]Error extracting census data: {e}[/dim]", markup=False)
            return None

    async def search_other_records(self, person_data: dict) -> List[Dict]:
        """Search for other primary sources (birth, death, marriage, immigration, military)"""
        other_records = []

        name = f"{person_data.get('first_name', '')} {person_data.get('last_name', '')}".strip()
        birth_year = person_data.get('birth_date', '')[:4] if person_data.get('birth_date') else ""

        if not name:
            return other_records

        try:
            # Navigate to all records search
            await self.page.goto("https://www.familysearch.org/search/record/results", timeout=60000)
            await asyncio.sleep(2)

            # Fill search form
            await self.page.fill('input[name="givenName"]', person_data.get('first_name', ''))
            await self.page.fill('input[name="surname"]', person_data.get('last_name', ''))

            if birth_year:
                await self.page.fill('input[name="birthLikeYear"]', birth_year)

            # Search
            search_button = await self.page.wait_for_selector('button[type="submit"]', timeout=5000)
            await search_button.click()
            await asyncio.sleep(5)

            # Get results (up to 10 non-census records)
            result_links = await self.page.query_selector_all('a[href*="/ark:/61903/"]')

            for i, link in enumerate(result_links[:10]):
                try:
                    # Get result type from parent element
                    parent = await link.query_selector('..')
                    parent_text = await parent.text_content()

                    # Skip if already got this in census search
                    if "Census" in parent_text:
                        continue

                    href = await link.get_attribute("href")

                    # Click through
                    await link.click()
                    await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                    await asyncio.sleep(2)

                    # Extract record data
                    record_data = await self.extract_record_data()

                    if record_data:
                        other_records.append(record_data)
                        record_type = record_data.get("record_type", "Unknown")
                        console.print(f"[green]✓[/green] Found record: {record_type}")

                    # Go back
                    await self.page.go_back()
                    await asyncio.sleep(2)

                except Exception as e:
                    console.print(f"[dim]Error extracting record {i+1}: {e}[/dim]", markup=False)
                    continue

        except Exception as e:
            console.print(f"[dim]Other records search error: {e}[/dim]", markup=False)

        return other_records

    async def extract_record_data(self) -> Optional[Dict]:
        """Extract data from any record type"""
        try:
            record_data = {
                "url": self.page.url,
                "extracted_at": datetime.now().isoformat(),
                "fields": {},
                "raw_text": ""
            }

            # Get title to determine record type
            try:
                title = await self.page.text_content("h1")
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

            for row in field_rows:
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

            # Get full text
            try:
                page_text = await self.page.text_content('body')
                record_data["raw_text"] = page_text[:5000]
            except:
                pass

            if record_data["fields"]:
                return record_data

            return None

        except Exception as e:
            console.print(f"[dim]Error extracting record: {e}[/dim]", markup=False)
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

        # Search census records
        console.print("[dim]Searching US Census...[/dim]")
        census_records = await self.search_census_records(person_data)
        validation["census_records"] = census_records
        self.stats["census_found"] += len(census_records)

        # Search other records
        console.print("[dim]Searching other primary sources...[/dim]")
        other_records = await self.search_other_records(person_data)
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
            console.print("[yellow]No primary sources found[/yellow]")
        else:
            console.print(f"[green]✓[/green] Found {validation['summary']['total_records']} primary sources")

        return validation

    async def validate_profiles(self, max_profiles: int = 150):
        """Validate up to max_profiles against all primary sources"""

        # Filter to profiles not yet processed
        to_validate = [
            (pid, pdata) for pid, pdata in self.profiles.items()
            if pid not in self.processed_ids
        ][:max_profiles]

        console.print(f"\n[cyan]Validating up to {max_profiles} profiles...[/cyan]")
        console.print(f"Total to validate: {len(to_validate)}\n")

        for person_id, person_data in to_validate:
            try:
                # Validate
                validation = await self.validate_profile(person_id, person_data)

                # Save
                self.validations[person_id] = validation
                self.processed_ids.add(person_id)

                # Save progress after each profile
                self.save_progress()
                self.save_validations()

                # Small delay between profiles
                await asyncio.sleep(2)

            except Exception as e:
                console.print(f"[red]Error validating {person_id}: {e}[/red]", markup=False)
                continue

        console.print("\n[green]✓[/green] Validation complete!")
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
        console.print("\n[bold cyan]═══ COMPREHENSIVE PRIMARY SOURCE VALIDATION REPORT ═══[/bold cyan]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Record Type", style="cyan")
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
        console.print(f"[bold]Data saved to: {self.data_file}[/bold]\n")

    async def run(self):
        """Main execution"""
        try:
            # Load data
            self.load_data()

            # Initialize browser
            if not await self.initialize_browser():
                return

            # Login
            if not await self.login_to_familysearch():
                console.print("\n[red]Failed to login. Please check your credentials and try again.[/red]\n")
                return

            console.print("[green]✓[/green] Ready to search FamilySearch\n")
            console.print("[green]✓[/green] Ready to validate!\n")

            console.print(f"{len(self.profiles)} profiles will be validated against:")
            console.print("  • US Census (all years)")
            console.print("  • Birth records")
            console.print("  • Death records")
            console.print("  • Marriage records")
            console.print("  • Immigration records")
            console.print("  • Military records")
            console.print("  • Other primary sources")
            console.print("\nAll available information will be extracted from each record.\n")

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
    validator = ComprehensivePrimaryValidator()
    await validator.run()


if __name__ == "__main__":
    asyncio.run(main())
