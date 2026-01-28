"""
FamilySearch Census Extractor using Playwright Browser Automation

This script opens FamilySearch in a browser, lets you login, then helps you
extract census data by navigating to your census records and scraping the data.

Usage:
    uv run python familysearch_login.py

The script will:
1. Open FamilySearch login page
2. Wait for you to login manually
3. Navigate to your person's census records
4. Extract census data
5. Auto-populate the YAML files
"""

import asyncio
from playwright.async_api import async_playwright
import yaml
from pathlib import Path
from datetime import datetime

# Configuration
PERSON_NAME = "John Jeffery"
BIRTH_YEAR = 1803
CENSUS_YEARS = [1841, 1851, 1861]

class FamilySearchExtractor:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None

    async def start_browser(self):
        """Start Playwright browser."""
        print("🌐 Starting browser...")
        self.playwright = await async_playwright().start()

        # Launch browser with visible window
        self.browser = await self.playwright.chromium.launch(
            headless=False,  # Show browser window
            slow_mo=500,     # Slow down for visibility
        )

        self.page = await self.browser.new_page()
        print("✓ Browser started")

    async def login(self):
        """Navigate to FamilySearch and wait for user to login."""
        print("\n🔐 Opening FamilySearch login page...")
        print("    Please login manually in the browser window")

        # Go to FamilySearch
        await self.page.goto("https://www.familysearch.org/auth/familysearch/login")

        # Wait for login to complete (user will be redirected to home page)
        print("⏳ Waiting for you to login...")
        print("    (The script will continue once you're logged in)")

        try:
            # Wait for URL to change away from login page (max 5 minutes)
            await self.page.wait_for_url(
                lambda url: "login" not in url.lower(),
                timeout=300000  # 5 minutes
            )
            print("✓ Login successful!")
            return True
        except Exception as e:
            print(f"✗ Login timeout or error: {e}")
            return False

    async def search_person(self, name, birth_year):
        """Search for the person in FamilySearch."""
        print(f"\n🔍 Searching for {name} (b. {birth_year})...")

        # Go to search page
        await self.page.goto("https://www.familysearch.org/search/")

        # Fill in search form
        await self.page.fill('input[name="givenName"]', name.split()[0])  # First name
        await self.page.fill('input[name="surname"]', name.split()[-1])   # Last name
        await self.page.fill('input[name="birthLikeYear"]', str(birth_year))

        # Submit search
        await self.page.click('button[type="submit"]')

        # Wait for results
        await self.page.wait_for_selector('.search-result')
        print("✓ Search results loaded")

        # Get first result (adjust if needed)
        first_result = await self.page.query_selector('.search-result a')
        if first_result:
            result_url = await first_result.get_attribute('href')
            print(f"✓ Found person: {result_url}")
            return result_url
        else:
            print("✗ No results found")
            return None

    async def navigate_to_census(self, person_url, year):
        """Navigate to a specific census record for the person."""
        print(f"\n📋 Looking for {year} census record...")

        # Go to person's page
        await self.page.goto(f"https://www.familysearch.org{person_url}")

        # Click on "Sources" tab
        await self.page.click('text=Sources')
        await asyncio.sleep(2)

        # Look for census record with matching year
        census_links = await self.page.query_selector_all(f'text=Census, {year}')

        if census_links:
            print(f"✓ Found {year} census record")
            await census_links[0].click()
            await asyncio.sleep(3)
            return True
        else:
            print(f"⚠️  No {year} census found attached to this person")
            return False

    async def extract_census_data(self, year):
        """Extract census data from the current page."""
        print(f"📝 Extracting {year} census data...")

        # Wait for census record to load
        await self.page.wait_for_load_state('networkidle')

        # Extract data using JavaScript
        data = await self.page.evaluate('''
            () => {
                // Look for census data in various possible formats
                const data = {
                    person: {},
                    household: [],
                    address: {},
                    citation: {}
                };

                // Try to find name
                const nameEl = document.querySelector('[data-test="name"], .name, h1');
                if (nameEl) data.person.name = nameEl.textContent.trim();

                // Try to find age
                const ageEl = document.querySelector('[data-test="age"], .age');
                if (ageEl) data.person.age = ageEl.textContent.trim();

                // Try to find birthplace
                const birthplaceEl = document.querySelector('[data-test="birthplace"], .birthplace');
                if (birthplaceEl) data.person.birthplace = birthplaceEl.textContent.trim();

                // Try to find occupation
                const occupationEl = document.querySelector('[data-test="occupation"], .occupation');
                if (occupationEl) data.person.occupation = occupationEl.textContent.trim();

                // Try to find household members
                const householdRows = document.querySelectorAll('table tbody tr, .household-member');
                householdRows.forEach(row => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 3) {
                        data.household.push({
                            name: cells[0]?.textContent.trim() || '',
                            age: cells[1]?.textContent.trim() || '',
                            relationship: cells[2]?.textContent.trim() || ''
                        });
                    }
                });

                // Try to find address
                const addressEl = document.querySelector('[data-test="address"], .address');
                if (addressEl) {
                    const addressText = addressEl.textContent.trim();
                    data.address.full = addressText;
                }

                // Get page URL for citation
                data.citation.url = window.location.href;

                return data;
            }
        ''')

        print(f"✓ Extracted data for {data['person'].get('name', 'Unknown')}")
        return data

    async def save_to_yaml(self, year, data):
        """Save extracted data to YAML file."""
        yaml_file = Path(f"census_{year}.yaml")

        # Build YAML structure
        census_data = {
            "census_year": year,
            "citation": {
                "collection": f"England and Wales Census, {year}",
                "registration_district": "",
                "sub_district": "",
                "enumeration_district": "",
                "piece": "",
                "folio": "",
                "page": "",
                "line": "",
                "familysearch_url": data["citation"].get("url", ""),
            },
            "person": {
                "name": data["person"].get("name", "John Jeffery"),
                "age": data["person"].get("age", ""),
                "sex": "M",
                "occupation": data["person"].get("occupation", ""),
                "birthplace": data["person"].get("birthplace", ""),
                "relationship_to_head": "Head" if year >= 1851 else "",
            },
            "household": [
                {
                    "name": member.get("name", ""),
                    "age": member.get("age", ""),
                    "relationship": member.get("relationship", ""),
                    "birthplace": "",
                }
                for member in data.get("household", [])
            ],
            "address": {
                "street": "",
                "parish": "",
                "township": "",
                "county": "",
            },
            "notes": f"Extracted automatically on {datetime.now().strftime('%Y-%m-%d %H:%M')}. Please review and fill in missing fields.",
        }

        # Save to file
        with open(yaml_file, 'w') as f:
            yaml.dump(census_data, f, default_flow_style=False, allow_unicode=True)

        print(f"✓ Saved to {yaml_file}")

    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


async def main():
    """Main extraction workflow."""
    extractor = FamilySearchExtractor()

    try:
        # Start browser
        await extractor.start_browser()

        # Login
        if not await extractor.login():
            print("\n❌ Login failed. Please try again.")
            return

        # Search for person
        person_url = await extractor.search_person(PERSON_NAME, BIRTH_YEAR)

        if not person_url:
            print("\n❌ Could not find person. Try searching manually and copy the URL.")
            input("Press Enter when you're on the person's page...")
            person_url = await extractor.page.url()

        # Extract each census
        for year in CENSUS_YEARS:
            print(f"\n{'='*60}")
            print(f"Processing {year} Census")
            print('='*60)

            if await extractor.navigate_to_census(person_url, year):
                data = await extractor.extract_census_data(year)
                await extractor.save_to_yaml(year, data)
            else:
                print(f"⚠️  Skipping {year} - census not found")

        print("\n" + "="*60)
        print("✅ EXTRACTION COMPLETE!")
        print("="*60)
        print("\nNext steps:")
        print("1. Review the generated census_YEAR.yaml files")
        print("2. Fill in any missing fields (especially citation details)")
        print("3. Run: uv run python analyze_census.py")

        # Keep browser open for manual review
        print("\n🌐 Browser will stay open for 30 seconds for you to review...")
        await asyncio.sleep(30)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await extractor.close()


if __name__ == "__main__":
    print("="*60)
    print("FamilySearch Census Extractor")
    print("="*60)
    print("\nThis script will:")
    print("1. Open FamilySearch in a browser")
    print("2. Let you login manually")
    print("3. Search for John Jeffery (b. 1803)")
    print("4. Extract census data from 1841, 1851, 1861")
    print("5. Save to census_YEAR.yaml files")
    print("\n⚠️  Make sure you have Playwright installed:")
    print("    uv add playwright")
    print("    uv run playwright install chromium")
    print("\nStarting in 3 seconds...")

    import time
    time.sleep(3)

    asyncio.run(main())
