"""Example: FamilySearch Browser Login.

Demonstrates username/password authentication using automated browser login.
"""
from __future__ import annotations

import asyncio
import os

from gps_agents.sources.familysearch_client import (
    ClientConfig,
    FamilySearchClient,
    SearchParams,
)


async def example_browser_login_from_env():
    """Login using credentials from environment variables."""
    print("=" * 60)
    print("Example 1: Browser login from environment variables")
    print("=" * 60)

    # Set credentials in environment
    # FAMILYSEARCH_USERNAME=your_email@example.com
    # FAMILYSEARCH_PASSWORD=your_password

    config = ClientConfig(client_id="example_client")

    async with FamilySearchClient(config) as client:
        # Login using browser automation (reads from env)
        print("Logging in via browser automation...")
        await client.login(method="browser")

        print(f"✓ Authenticated: {client.is_authenticated}")

        # Perform a search
        print("\nSearching for 'Durham' in North Carolina...")
        params = SearchParams(surname="Durham", birth_place="North Carolina", count=5)
        results = await client.search_persons(params)

        print(f"Found {results.total_results} total results")
        for person in results.all_persons[:5]:
            print(f"  - {person.display_name} ({person.birth_date})")


async def example_browser_login_explicit():
    """Login with explicit credentials."""
    print("\n" + "=" * 60)
    print("Example 2: Browser login with explicit credentials")
    print("=" * 60)

    config = ClientConfig(client_id="example_client")

    async with FamilySearchClient(config) as client:
        # Login with explicit credentials
        username = os.getenv("FAMILYSEARCH_USERNAME", "your_email@example.com")
        password = os.getenv("FAMILYSEARCH_PASSWORD", "your_password")

        print("Logging in via browser automation...")
        await client.login(username=username, password=password)

        print(f"✓ Authenticated: {client.is_authenticated}")


async def example_browser_login_headful():
    """Login with visible browser (for debugging)."""
    print("\n" + "=" * 60)
    print("Example 3: Browser login with visible browser")
    print("=" * 60)

    config = ClientConfig(client_id="example_client")

    async with FamilySearchClient(config) as client:
        # Login with browser visible (headless=False)
        print("Opening browser (you'll see it)...")
        await client.auth.login_with_browser(headless=False)

        print(f"✓ Authenticated: {client.is_authenticated}")


async def example_token_persistence():
    """Demonstrate token persistence across sessions."""
    print("\n" + "=" * 60)
    print("Example 4: Token persistence")
    print("=" * 60)

    config = ClientConfig(
        client_id="example_client",
        token_file="data/my_fs_token.json",  # Custom token file
    )

    # First session: Login and save token
    print("Session 1: Login and save token...")
    async with FamilySearchClient(config) as client:
        await client.login(method="browser")
        print(f"✓ Authenticated and token saved to {config.token_file}")

    # Second session: Reuse saved token
    print("\nSession 2: Reuse saved token...")
    async with FamilySearchClient(config) as client:
        # Token is automatically loaded
        print(f"✓ Token loaded: {client.is_authenticated}")

        if client.is_authenticated:
            print("No login needed - using saved token!")
        else:
            print("Token expired, need to login again")


async def main():
    """Run all examples."""
    print("FamilySearch Browser Login Examples")
    print("=" * 60)
    print("\nNOTE: Make sure to set environment variables:")
    print("  export FAMILYSEARCH_USERNAME=your_email@example.com")
    print("  export FAMILYSEARCH_PASSWORD=your_password")
    print()

    # Check if credentials are set
    if not os.getenv("FAMILYSEARCH_USERNAME") or not os.getenv("FAMILYSEARCH_PASSWORD"):
        print("⚠️  Warning: Credentials not found in environment")
        print("   Set FAMILYSEARCH_USERNAME and FAMILYSEARCH_PASSWORD")
        return

    try:
        # Run examples
        await example_browser_login_from_env()
        # await example_browser_login_explicit()
        # await example_browser_login_headful()  # Uncomment to see browser
        # await example_token_persistence()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
