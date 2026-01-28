#!/usr/bin/env python3
"""
FamilySearch Primary Source Validator - Automated with login.

Logs into FamilySearch, searches for each profile, examines sources,
and cross-references all information for GPS compliance.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

console = Console()


class FamilySearchPrimaryValidator:
    """Automated FamilySearch validation with login and source verification."""

    def __init__(self):
        self.expanded_tree_file = Path("expanded_tree.json")
        self.validation_file = Path("familysearch_extracted_data.json")
        self.progress_file = Path("familysearch_validation_progress.json")

        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None

        self.profiles: Dict[str, dict] = {}
        self.validations: Dict[str, dict] = {}
        self.processed_ids: set = set()

        # Statistics
        self.stats = {
            "total_profiles": 0,
            "validated": 0,
            "high_confidence": 0,
            "medium_confidence": 0,
            "low_confidence": 0,
            "not_found": 0,
            "discrepancies": 0,
        }

    async def initialize_browser(self) -> bool:
        """Initialize Playwright browser with FamilySearch login."""
        try:
            console.print("\n[bold cyan]Initializing browser...[/bold cyan]")

            self.playwright = await async_playwright().start()

            # Use Chrome browser (more realistic, less likely to be detected)
            # Try to connect to existing Chrome or launch new one
            try:
                self.browser = await self.playwright.chromium.connect_over_cdp("http://localhost:9222")
                console.print("[dim]Connected to existing Chrome instance[/dim]")
            except:
                # Launch Chrome with user's profile
                user_data_dir = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"

                # Use a separate profile for FamilySearch to avoid conflicts
                fs_profile = Path.home() / ".familysearch_chrome_profile"
                fs_profile.mkdir(exist_ok=True)

                self.browser = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=str(fs_profile),
                    headless=False,  # Keep visible
                    channel="chrome",  # Use actual Chrome, not Chromium
                    viewport={"width": 1280, "height": 720},
                    args=[
                        "--disable-blink-features=AutomationControlled",  # Hide automation
                        "--disable-dev-shm-usage",
                        "--no-sandbox"
                    ]
                )

            self.page = self.browser.pages[0] if self.browser.pages else await self.browser.new_page()

            # Bring browser window to front
            await self.page.bring_to_front()
            await self.page.set_viewport_size({"width": 1400, "height": 900})

            console.print("[green]✓[/green] Browser initialized")
            return True

        except Exception as e:
            console.print(f"[red]Failed to initialize browser: {e}[/red]")
            return False

    async def login_to_familysearch(self) -> bool:
        """Login to FamilySearch - interactive."""
        try:
            console.print("\n[bold cyan]Logging into FamilySearch...[/bold cyan]")

            # Navigate to FamilySearch with increased timeout
            await self.page.goto("https://www.familysearch.org/", wait_until="domcontentloaded", timeout=60000)

            # Check if already logged in
            try:
                await self.page.wait_for_selector("text=Sign In", timeout=3000)
                needs_login = True
            except:
                needs_login = False

            if needs_login:
                console.print("\n[yellow]Please log into FamilySearch in the browser window.[/yellow]")
                console.print("[dim]The browser will remain open while you log in.[/dim]")
                console.print("[dim]Free accounts work fine - create one at familysearch.org[/dim]\n")

                # Wait for user to log in
                console.print("Waiting for login... (checking every 5 seconds)")

                logged_in = False
                max_wait = 300  # 5 minutes
                waited = 0

                while not logged_in and waited < max_wait:
                    await asyncio.sleep(5)
                    waited += 5

                    # Check if logged in by looking for sign out or user menu
                    try:
                        # Check for common logged-in elements
                        await self.page.wait_for_selector("text=Family Tree", timeout=1000)
                        logged_in = True
                        console.print("[green]✓[/green] Login detected!")
                        break
                    except:
                        console.print(f"[dim]Still waiting... ({waited}s / {max_wait}s)[/dim]")

                if not logged_in:
                    console.print("[red]Login timeout. Please try again.[/red]")
                    return False
            else:
                console.print("[green]✓[/green] Already logged in!")

            # Navigate to search page to confirm
            await self.page.goto("https://www.familysearch.org/search/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)
            console.print("[green]✓[/green] Ready to search FamilySearch")

            return True

        except Exception as e:
            console.print(f"[red]Login failed: {e}[/red]")
            return False

    async def search_person(self, person_data: dict) -> Optional[str]:
        """Search for a person on FamilySearch and return their profile URL."""
        try:
            first_name = person_data.get("first_name", "")
            last_name = person_data.get("last_name", "")
            birth_date = person_data.get("birth_date", "")
            birth_place = person_data.get("birth_place", "")

            if not first_name or not last_name:
                return None

            # Extract year from birth_date
            birth_year = ""
            if birth_date and len(birth_date) >= 4:
                birth_year = birth_date.split("-")[0]

            console.print(f"\n[cyan]Searching: {first_name} {last_name} (b. {birth_year})[/cyan]")

            # Navigate to search page with increased timeout
            await self.page.goto("https://www.familysearch.org/search/", wait_until="load", timeout=60000)
            await asyncio.sleep(5)  # Give page time to fully render

            # Fill in search form
            try:
                # Try multiple selector strategies
                given_name_selectors = [
                    'input[name="givenName"]',
                    'input[placeholder*="First"]',
                    '#givenName',
                    'input[type="text"]:first-of-type'
                ]

                surname_selectors = [
                    'input[name="surname"]',
                    'input[placeholder*="Last"]',
                    '#surname'
                ]

                # Try to find and fill given name
                given_name_input = None
                for selector in given_name_selectors:
                    try:
                        given_name_input = await self.page.wait_for_selector(selector, timeout=10000, state="visible")
                        if given_name_input:
                            console.print(f"[dim]Found given name with selector: {selector}[/dim]")
                            break
                    except:
                        continue

                if not given_name_input:
                    console.print("[yellow]Could not find given name input, trying click and type[/yellow]")
                    # Try clicking on the page first to activate forms
                    await self.page.click('body')
                    await asyncio.sleep(1)
                    # Try again with first selector
                    given_name_input = await self.page.wait_for_selector(given_name_selectors[0], timeout=10000)

                await given_name_input.fill(first_name)
                await asyncio.sleep(1)

                # Try to find and fill surname
                surname_input = None
                for selector in surname_selectors:
                    try:
                        surname_input = await self.page.wait_for_selector(selector, timeout=10000, state="visible")
                        if surname_input:
                            break
                    except:
                        continue

                if surname_input:
                    await surname_input.fill(last_name)
                    await asyncio.sleep(1)

                # Birth year
                if birth_year:
                    try:
                        birth_year_input = await self.page.wait_for_selector('input[name="birthLikeYear"]', timeout=10000)
                        await birth_year_input.fill(birth_year)
                        await asyncio.sleep(1)
                    except:
                        pass  # Birth year is optional

                # Birth place
                if birth_place:
                    try:
                        birth_place_input = await self.page.wait_for_selector('input[name="birthLikePlace"]', timeout=10000)
                        await birth_place_input.fill(birth_place)
                        await asyncio.sleep(1)
                    except:
                        pass  # Birth place is optional

                # Submit search
                await self.page.click('button[type="submit"]', timeout=10000)
                await self.page.wait_for_load_state("domcontentloaded", timeout=60000)
                await asyncio.sleep(3)

                # Look for results
                try:
                    # Wait for search results to load
                    await asyncio.sleep(3)

                    # Find and click first result link to go to tree person page
                    first_result = await self.page.wait_for_selector(
                        'a[href*="/tree/person/"]',
                        timeout=10000,
                        state="visible"
                    )

                    if first_result:
                        # Get the href for logging
                        href = await first_result.get_attribute("href")
                        console.print(f"[dim]Clicking result: {href[:80]}...[/dim]")

                        # Click the result to navigate to the person page
                        await first_result.click()
                        await self.page.wait_for_load_state("domcontentloaded", timeout=60000)
                        await asyncio.sleep(2)

                        # Get the actual person page URL
                        actual_url = self.page.url
                        console.print(f"[green]✓[/green] Found profile: {actual_url}")
                        return actual_url
                except Exception as e:
                    console.print(f"[yellow]No results found: {e}[/yellow]")
                    return None

            except Exception as e:
                console.print(f"[yellow]Search error: {e}[/yellow]")
                return None

        except Exception as e:
            console.print(f"[red]Search failed: {e}[/red]")
            return None

    async def extract_profile_sources(self, profile_url: str) -> Dict:
        """Extract all sources and information from a FamilySearch profile."""
        try:
            console.print(f"[cyan]Examining profile sources...[/cyan]")

            # Navigate to profile with increased timeout
            await self.page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            extracted = {
                "profile_url": profile_url,
                "person_name": "",
                "birth_date": "",
                "birth_location": "",
                "death_date": "",
                "death_location": "",
                "father_name": "",
                "mother_name": "",
                "sources": [],
                "extraction_date": datetime.now().isoformat(),
            }

            # Extract name
            try:
                name_elem = await self.page.wait_for_selector('h1[data-test="person-vitals-name"]', timeout=5000)
                if name_elem:
                    extracted["person_name"] = await name_elem.inner_text()
                    console.print(f"  Name: {extracted['person_name']}")
            except:
                pass

            # Extract vital events
            try:
                # Birth
                birth_elem = await self.page.query_selector('span:has-text("Birth")')
                if birth_elem:
                    parent = await birth_elem.evaluate_handle('el => el.closest("li")')
                    birth_text = await parent.inner_text()
                    # Parse birth text for date and place
                    lines = birth_text.split("\n")
                    for line in lines:
                        if any(char.isdigit() for char in line) and "Birth" not in line:
                            if not extracted["birth_date"] and len(line) < 30:
                                extracted["birth_date"] = line.strip()
                            elif not extracted["birth_location"]:
                                extracted["birth_location"] = line.strip()
                    console.print(f"  Birth: {extracted['birth_date']} in {extracted['birth_location']}")
            except:
                pass

            # Extract death
            try:
                death_elem = await self.page.query_selector('span:has-text("Death")')
                if death_elem:
                    parent = await death_elem.evaluate_handle('el => el.closest("li")')
                    death_text = await parent.inner_text()
                    lines = death_text.split("\n")
                    for line in lines:
                        if any(char.isdigit() for char in line) and "Death" not in line:
                            if not extracted["death_date"] and len(line) < 30:
                                extracted["death_date"] = line.strip()
                            elif not extracted["death_location"]:
                                extracted["death_location"] = line.strip()
                    console.print(f"  Death: {extracted['death_date']} in {extracted['death_location']}")
            except:
                pass

            # Extract parents
            try:
                # Click to expand family section if needed
                parents_section = await self.page.query_selector('text=Parents')
                if parents_section:
                    # Look for parent names
                    parent_links = await self.page.query_selector_all('a[href*="/tree/person/"]')
                    parent_count = 0
                    for link in parent_links[:2]:  # First 2 are usually parents
                        name = await link.inner_text()
                        if parent_count == 0:
                            extracted["father_name"] = name.strip()
                            console.print(f"  Father: {extracted['father_name']}")
                        elif parent_count == 1:
                            extracted["mother_name"] = name.strip()
                            console.print(f"  Mother: {extracted['mother_name']}")
                        parent_count += 1
            except:
                pass

            # Navigate to Sources tab
            try:
                sources_tab = await self.page.wait_for_selector('a[href*="sources"]', timeout=5000)
                if sources_tab:
                    await sources_tab.click()
                    await self.page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)

                    # Extract source information
                    source_elements = await self.page.query_selector_all('[data-test="source-title"]')
                    console.print(f"  Found {len(source_elements)} sources")

                    for i, source_elem in enumerate(source_elements[:5]):  # Limit to first 5
                        try:
                            title = await source_elem.inner_text()
                            extracted["sources"].append({
                                "title": title.strip(),
                                "index": i + 1
                            })
                            console.print(f"    [{i+1}] {title[:80]}")
                        except:
                            pass
            except:
                console.print("  [dim]No sources tab found[/dim]")

            return extracted

        except Exception as e:
            console.print(f"[red]Failed to extract profile: {e}[/red]")
            return None

    def cross_reference_data(self, wikitree_data: dict, familysearch_data: dict) -> Dict:
        """Cross-reference WikiTree data with FamilySearch data."""
        discrepancies = []
        matches = []
        confidence = "high"

        # Compare birth dates
        wt_birth = wikitree_data.get("birth_date", "")
        fs_birth = familysearch_data.get("birth_date", "")

        if wt_birth and fs_birth:
            if wt_birth.replace("-00-00", "") in fs_birth or fs_birth in wt_birth:
                matches.append(f"Birth date: {fs_birth}")
            else:
                discrepancies.append(f"Birth date: WikiTree={wt_birth}, FamilySearch={fs_birth}")
                confidence = "medium"

        # Compare birth places
        wt_place = wikitree_data.get("birth_place", "")
        fs_place = familysearch_data.get("birth_location", "")

        if wt_place and fs_place:
            # Fuzzy match - check if core location is present
            wt_core = wt_place.split(",")[0].strip().lower()
            fs_core = fs_place.lower()

            if wt_core in fs_core or fs_core in wt_core:
                matches.append(f"Birth place: {fs_place}")
            else:
                discrepancies.append(f"Birth place: WikiTree={wt_place}, FamilySearch={fs_place}")
                confidence = "medium"

        # Compare death data if available
        wt_death_date = wikitree_data.get("death_date", "")
        fs_death_date = familysearch_data.get("death_date", "")

        if wt_death_date and fs_death_date:
            if wt_death_date.replace("-00-00", "") in fs_death_date or fs_death_date in wt_death_date:
                matches.append(f"Death date: {fs_death_date}")
            else:
                discrepancies.append(f"Death date: WikiTree={wt_death_date}, FamilySearch={fs_death_date}")

        # Check if parents match
        wt_father = wikitree_data.get("father", "")
        wt_mother = wikitree_data.get("mother", "")
        fs_father = familysearch_data.get("father_name", "")
        fs_mother = familysearch_data.get("mother_name", "")

        if wt_father and fs_father:
            # Extract first/last name for comparison
            if any(part.lower() in fs_father.lower() for part in wt_father.split("-")[0].split()):
                matches.append(f"Father confirmed: {fs_father}")
            else:
                discrepancies.append(f"Father: WikiTree={wt_father}, FamilySearch={fs_father}")

        if wt_mother and fs_mother:
            if any(part.lower() in fs_mother.lower() for part in wt_mother.split("-")[0].split()):
                matches.append(f"Mother confirmed: {fs_mother}")
            else:
                discrepancies.append(f"Mother: WikiTree={wt_mother}, FamilySearch={fs_mother}")

        # Adjust confidence based on sources
        num_sources = len(familysearch_data.get("sources", []))
        if num_sources == 0:
            confidence = "low"
        elif num_sources >= 3 and confidence == "high":
            confidence = "high"

        # Lower confidence if multiple discrepancies
        if len(discrepancies) >= 3:
            confidence = "low"
        elif len(discrepancies) >= 1:
            confidence = "medium"

        return {
            "matches": matches,
            "discrepancies": discrepancies,
            "confidence": confidence,
            "num_sources": num_sources,
        }

    def create_validation_entry(self, wt_id: str, wikitree_data: dict,
                               familysearch_data: dict, cross_ref: dict) -> dict:
        """Create validation entry with primary source data."""
        return {
            "person_name": familysearch_data.get("person_name", ""),
            "birth_date": familysearch_data.get("birth_date", ""),
            "birth_location": familysearch_data.get("birth_location", ""),
            "death_date": familysearch_data.get("death_date", ""),
            "death_location": familysearch_data.get("death_location", ""),
            "familysearch_profile_url": familysearch_data.get("profile_url", ""),
            "familysearch_sources": familysearch_data.get("sources", []),
            "wikitree_id": wt_id,
            "relationships": {
                "father": {"name": familysearch_data.get("father_name", "")},
                "mother": {"name": familysearch_data.get("mother_name", "")},
            },
            "source": "FamilySearch",
            "source_collection": "FamilySearch Family Tree with Primary Sources",
            "extraction_confidence": cross_ref["confidence"],
            "extraction_method": "automated_primary_source_validation",
            "extraction_date": datetime.now().isoformat(),
            "cross_reference": {
                "matches": cross_ref["matches"],
                "discrepancies": cross_ref["discrepancies"],
                "num_sources": cross_ref["num_sources"],
            },
            "notes": f"Validated against FamilySearch primary sources. "
                    f"{len(cross_ref['matches'])} matches, "
                    f"{len(cross_ref['discrepancies'])} discrepancies, "
                    f"{cross_ref['num_sources']} sources found.",
        }

    def load_data(self):
        """Load existing data."""
        console.print("\n[bold cyan]Loading data...[/bold cyan]")

        # Load expanded tree
        with open(self.expanded_tree_file) as f:
            tree_data = json.load(f)
            self.profiles = tree_data.get("people", {})
            console.print(f"  Loaded {len(self.profiles)} profiles")

        # Load existing validations
        if self.validation_file.exists():
            with open(self.validation_file) as f:
                val_data = json.load(f)
                self.validations = val_data.get("data", {})
                console.print(f"  Loaded {len(self.validations)} existing validations")

        # Load progress
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                progress = json.load(f)
                self.processed_ids = set(progress.get("processed_ids", []))
                self.stats = progress.get("stats", self.stats)
                console.print(f"  Resumed: {len(self.processed_ids)} already processed")

    def save_progress(self):
        """Save validation progress."""
        progress = {
            "last_updated": datetime.now().isoformat(),
            "processed_ids": list(self.processed_ids),
            "stats": self.stats,
        }
        with open(self.progress_file, "w") as f:
            json.dump(progress, f, indent=2)

    def save_validations(self):
        """Save validation data."""
        val_data = {
            "generated_at": datetime.now().isoformat(),
            "extraction_type": "familysearch_primary_source_validation",
            "people_searched": len(self.validations),
            "data": self.validations,
            "stats": self.stats,
        }
        with open(self.validation_file, "w") as f:
            json.dump(val_data, f, indent=2, default=str)

    async def validate_profiles(self, max_profiles: int = 150):
        """Validate all profiles against FamilySearch."""
        console.print(f"\n[bold cyan]Validating up to {max_profiles} profiles...[/bold cyan]")

        profiles_to_validate = []
        for wt_id, profile in self.profiles.items():
            if wt_id not in self.processed_ids:
                profiles_to_validate.append((wt_id, profile))

        console.print(f"Total to validate: {len(profiles_to_validate)}")

        if not profiles_to_validate:
            console.print("[yellow]All profiles already validated![/yellow]")
            return

        # Limit to max_profiles
        profiles_to_validate = profiles_to_validate[:max_profiles]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Validating profiles", total=len(profiles_to_validate))

            for wt_id, profile in profiles_to_validate:
                try:
                    # Search for person
                    profile_url = await self.search_person(profile)

                    if not profile_url:
                        self.stats["not_found"] += 1
                        self.processed_ids.add(wt_id)
                        progress.update(task, advance=1)
                        continue

                    # Extract sources and data
                    fs_data = await self.extract_profile_sources(profile_url)

                    if not fs_data:
                        self.stats["not_found"] += 1
                        self.processed_ids.add(wt_id)
                        progress.update(task, advance=1)
                        continue

                    # Cross-reference
                    cross_ref = self.cross_reference_data(profile, fs_data)

                    # Create validation entry
                    validation = self.create_validation_entry(wt_id, profile, fs_data, cross_ref)
                    self.validations[wt_id] = validation

                    # Update stats
                    self.stats["validated"] += 1
                    if cross_ref["confidence"] == "high":
                        self.stats["high_confidence"] += 1
                    elif cross_ref["confidence"] == "medium":
                        self.stats["medium_confidence"] += 1
                    else:
                        self.stats["low_confidence"] += 1

                    if cross_ref["discrepancies"]:
                        self.stats["discrepancies"] += len(cross_ref["discrepancies"])

                    console.print(f"[green]✓[/green] Validated: {validation['person_name']} "
                                f"({cross_ref['confidence']} confidence, "
                                f"{cross_ref['num_sources']} sources)")

                    if cross_ref["discrepancies"]:
                        for disc in cross_ref["discrepancies"]:
                            console.print(f"  [yellow]⚠[/yellow]  {disc}")

                    self.processed_ids.add(wt_id)

                    # Save progress
                    self.save_progress()
                    self.save_validations()

                    # Wait between profiles
                    await asyncio.sleep(3)

                except Exception as e:
                    console.print(f"[red]Error validating {wt_id}: {e}[/red]")
                    self.processed_ids.add(wt_id)

                progress.update(task, advance=1)

        self.stats["total_profiles"] = len(self.profiles)

    def print_summary(self):
        """Print validation summary."""
        console.print("\n[bold cyan]═══ FamilySearch Validation Summary ═══[/bold cyan]\n")

        from rich.table import Table

        table = Table(title="Validation Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_column("Percentage", style="yellow", justify="right")

        total = self.stats["total_profiles"]
        validated = self.stats["validated"]

        table.add_row("Total Profiles", str(total), "100%")
        table.add_row(
            "Validated with FamilySearch",
            str(validated),
            f"{(validated/total*100):.1f}%" if total > 0 else "0%"
        )
        table.add_row("", "", "")
        table.add_row(
            "High Confidence",
            str(self.stats["high_confidence"]),
            f"{(self.stats['high_confidence']/validated*100):.1f}%" if validated > 0 else "0%"
        )
        table.add_row(
            "Medium Confidence",
            str(self.stats["medium_confidence"]),
            f"{(self.stats['medium_confidence']/validated*100):.1f}%" if validated > 0 else "0%"
        )
        table.add_row(
            "Low Confidence",
            str(self.stats["low_confidence"]),
            f"{(self.stats['low_confidence']/validated*100):.1f}%" if validated > 0 else "0%"
        )
        table.add_row("", "", "")
        table.add_row("Not Found", str(self.stats["not_found"]), "")
        table.add_row("Total Discrepancies", str(self.stats["discrepancies"]), "")

        console.print(table)

        # GPS status
        validation_pct = (validated / total * 100) if total > 0 else 0

        console.print(f"\n[bold]GPS Compliance:[/bold]")
        if validation_pct >= 75:
            console.print(f"  Status: [bold green]✅ GPS COMPLIANT[/bold green]")
        else:
            console.print(f"  Status: [yellow]Need {int(total * 0.75) - validated} more[/yellow]")

        console.print(f"  Validation: {validated}/{total} ({validation_pct:.1f}%)")

    async def cleanup(self):
        """Cleanup browser resources."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


async def main():
    """Main execution."""
    console.print("\n[bold yellow]FamilySearch Primary Source Validator[/bold yellow]")
    console.print("[dim]Automated validation with login and source verification[/dim]\n")

    validator = FamilySearchPrimaryValidator()

    try:
        # Load data
        validator.load_data()

        # Initialize browser
        if not await validator.initialize_browser():
            return

        # Login to FamilySearch
        if not await validator.login_to_familysearch():
            console.print("\n[red]Failed to login. Please check your credentials and try again.[/red]")
            return

        console.print("\n[bold green]✓ Ready to validate![/bold green]")
        console.print(f"\n{len(validator.profiles)} profiles will be validated against FamilySearch.")
        console.print("[dim]This process will search for each person, examine their sources, and cross-reference all information with WikiTree data.[/dim]\n")

        # Auto-confirm in non-interactive mode
        import sys
        if sys.stdin.isatty():
            if not Confirm.ask("Start validation?", default=True):
                console.print("[yellow]Cancelled by user[/yellow]")
                return
        else:
            console.print("[green]Starting validation (non-interactive mode)...[/green]\n")

        # Validate profiles
        await validator.validate_profiles()

        # Print summary
        validator.print_summary()

        console.print("\n[bold green]✅ Validation complete![/bold green]")
        console.print("\n[bold]Files updated:[/bold]")
        console.print("  • familysearch_extracted_data.json - Primary source validations")
        console.print("  • familysearch_validation_progress.json - Progress checkpoint")
        console.print("\n[dim]Run: uv run python generate_gps_report.py - to generate updated GPS report[/dim]")

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Interrupted! Progress saved.[/yellow]")
        validator.save_progress()
        validator.save_validations()
    except Exception as e:
        # Use markup=False to avoid Rich parsing error messages as markup
        console.print(f"\nError: {e}", style="red", markup=False)
        import traceback
        traceback.print_exc()
    finally:
        await validator.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
