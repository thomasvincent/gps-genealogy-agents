# FamilySearch Browser Authentication

This document explains how to use automated browser login for FamilySearch with username and password credentials.

## Overview

The FamilySearch client now supports three authentication methods:

1. **OAuth2 Flow** (default) - Opens browser for interactive authorization
2. **Browser Automation** (new) - Automated login with username/password
3. **Direct Token** - Use an existing access token

## Quick Start

### 1. Install Playwright Browsers

```bash
uv run playwright install chromium
```

### 2. Set Credentials

Set your FamilySearch credentials as environment variables:

```bash
export FAMILYSEARCH_USERNAME="your_email@example.com"
export FAMILYSEARCH_PASSWORD="your_password"
```

### 3. Use Browser Login

```python
from gps_agents.sources.familysearch_client import (
    ClientConfig,
    FamilySearchClient,
    SearchParams,
)

async def main():
    config = ClientConfig(client_id="your_app")

    async with FamilySearchClient(config) as client:
        # Login via browser automation
        await client.login(method="browser")

        # Now you can use the client
        params = SearchParams(surname="Durham", birth_place="North Carolina")
        results = await client.search_persons(params)

        for person in results.all_persons:
            print(f"{person.display_name} - {person.birth_date}")
```

## Credential Loading Priority

Credentials are loaded with the following priority (highest to lowest):

1. **Function parameters** - Passed directly to `login()`
2. **Environment variables** - `FAMILYSEARCH_USERNAME` and `FAMILYSEARCH_PASSWORD`
3. **Config file** - `data/credentials.json`

### Example: Function Parameters

```python
await client.login(
    username="user@example.com",
    password="secret123",
    method="browser"
)
```

### Example: Environment Variables

```bash
export FAMILYSEARCH_USERNAME="user@example.com"
export FAMILYSEARCH_PASSWORD="secret123"
```

```python
await client.login(method="browser")  # Reads from env
```

### Example: Config File

Create `data/credentials.json`:

```json
{
  "familysearch_username": "user@example.com",
  "familysearch_password": "secret123"
}
```

```python
await client.login(method="browser")  # Reads from config if env not set
```

## Authentication Methods

### Method 1: Browser Automation (Username/Password)

Best for: Automated scripts, testing, CI/CD

```python
config = ClientConfig(client_id="your_app")

async with FamilySearchClient(config) as client:
    # Automatic detection - if username/password provided, uses browser
    await client.login(username="user@example.com", password="secret")

    # Or explicitly specify method
    await client.login(method="browser")
```

**Advantages:**
- No OAuth app registration needed
- Works in headless environments
- Supports CI/CD workflows
- Credentials can be in environment or config

**Considerations:**
- Requires Playwright installation
- Browser automation may be slower than OAuth
- Check FamilySearch Terms of Service

### Method 2: OAuth2 Interactive Flow

Best for: Desktop applications, interactive use

```python
async with FamilySearchClient(config) as client:
    # Opens browser for user to authorize
    await client.login()  # method="oauth" is default
```

### Method 3: Direct Token

Best for: Already have a valid token

```python
async with FamilySearchClient(config) as client:
    await client.login(access_token="your_existing_token")
```

## Advanced Usage

### Headless vs Headed Browser

By default, the browser runs in headless mode (not visible). For debugging, you can show the browser:

```python
# Show browser window (for debugging)
await client.auth.login_with_browser(headless=False)
```

### Custom Timeout

Increase timeout for slow networks:

```python
config = ClientConfig(
    client_id="your_app",
    timeout=60.0,  # 60 seconds
)
```

### Token Persistence

Tokens are automatically saved and reused:

```python
config = ClientConfig(
    client_id="your_app",
    token_file="data/my_token.json",  # Custom location
)

# First time: Login required
async with FamilySearchClient(config) as client:
    await client.login(method="browser")
    # Token saved to data/my_token.json

# Later: Token automatically loaded
async with FamilySearchClient(config) as client:
    # No login needed - token loaded automatically
    if client.is_authenticated:
        print("Using saved token!")
```

### MCP Browser Integration

If you're using the MCP browser server:

```python
# MCP tools from your MCP setup
mcp_tools = {
    "browser_navigate": ...,
    "browser_type": ...,
    "browser_click": ...,
    "browser_evaluate": ...,
}

await client.auth.login_with_browser(
    username="user@example.com",
    password="secret",
    use_mcp=True,
    mcp_tools=mcp_tools,
)
```

## Security Best Practices

### 1. Never Hardcode Credentials

❌ **Bad:**
```python
await client.login(username="user@example.com", password="mypassword")
```

✅ **Good:**
```python
import os
username = os.getenv("FAMILYSEARCH_USERNAME")
password = os.getenv("FAMILYSEARCH_PASSWORD")
await client.login(username=username, password=password)
```

### 2. Use Environment Variables

Store credentials in `.env` file (never commit to git):

```bash
# .env
FAMILYSEARCH_USERNAME=your_email@example.com
FAMILYSEARCH_PASSWORD=your_password
```

Load with `python-dotenv`:

```python
from dotenv import load_dotenv
load_dotenv()

# Now env vars are available
await client.login(method="browser")
```

### 3. Restrict File Permissions

If using config file:

```bash
# Create config with restricted permissions
touch data/credentials.json
chmod 600 data/credentials.json
```

### 4. Add to .gitignore

```gitignore
# .gitignore
.env
data/credentials.json
data/*_token.json
```

## Troubleshooting

### Error: "No FamilySearch credentials found"

**Cause:** Credentials not provided in params, env, or config file.

**Solution:** Set environment variables:
```bash
export FAMILYSEARCH_USERNAME="your_email"
export FAMILYSEARCH_PASSWORD="your_password"
```

### Error: "Playwright browsers not installed"

**Cause:** Playwright browsers not installed.

**Solution:**
```bash
uv run playwright install chromium
```

### Error: "Login failed: Invalid credentials"

**Cause:** Incorrect username or password.

**Solution:** Verify credentials are correct. Try logging in manually at familysearch.org to test.

### Error: "Failed to extract access token"

**Cause:** FamilySearch page structure changed or unexpected error during login.

**Solution:**
1. Try with headless=False to see what's happening:
   ```python
   await client.auth.login_with_browser(headless=False)
   ```
2. Check if FamilySearch is working normally
3. File an issue if problem persists

### Timeout Errors

**Cause:** Slow network or page taking too long to load.

**Solution:** Increase timeout:
```python
config = ClientConfig(client_id="app", timeout=60.0)
```

## Complete Example

```python
"""Complete example of FamilySearch browser authentication."""
import asyncio
import os
from dotenv import load_dotenv

from gps_agents.sources.familysearch_client import (
    ClientConfig,
    FamilySearchClient,
    SearchParams,
)

async def main():
    # Load credentials from .env file
    load_dotenv()

    # Configure client
    config = ClientConfig(
        client_id="my_app",
        token_file="data/fs_token.json",
        timeout=30.0,
    )

    async with FamilySearchClient(config) as client:
        # Login (reads from environment)
        print("Logging in to FamilySearch...")
        await client.login(method="browser")

        if not client.is_authenticated:
            print("Login failed!")
            return

        print("✓ Authenticated successfully!")

        # Search for records
        print("\nSearching for Durham family in North Carolina...")
        params = SearchParams(
            surname="Durham",
            birth_place="North Carolina",
            birth_year=1900,
            birth_year_range=10,
            count=10,
        )

        results = await client.search_persons(params)

        print(f"\nFound {results.total_results} total results")
        print("\nFirst 10 matches:")
        for i, person in enumerate(results.all_persons[:10], 1):
            birth = person.birth_date.original if person.birth_date else "Unknown"
            place = person.birth_place.original if person.birth_place else "Unknown"
            print(f"{i}. {person.display_name}")
            print(f"   Birth: {birth}, {place}")

if __name__ == "__main__":
    asyncio.run(main())
```

## API Reference

### `FamilySearchClient.login()`

```python
await client.login(
    access_token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    method: str = "oauth",
)
```

**Parameters:**
- `access_token`: Direct token (for method="token")
- `username`: Username for browser login
- `password`: Password for browser login
- `method`: "oauth" | "browser" | "token"

**Returns:** None

**Raises:** `ValueError` if credentials missing or login fails

### `Authenticator.login_with_browser()`

```python
await auth.login_with_browser(
    username: str | None = None,
    password: str | None = None,
    headless: bool = True,
    use_mcp: bool = False,
    mcp_tools: dict | None = None,
)
```

**Parameters:**
- `username`: FamilySearch username (optional if in env/config)
- `password`: FamilySearch password (optional if in env/config)
- `headless`: Run browser in headless mode (default: True)
- `use_mcp`: Use MCP browser instead of Playwright (default: False)
- `mcp_tools`: MCP tool functions (required if use_mcp=True)

**Returns:** `TokenResponse`

**Raises:** `ValueError` if credentials not found or login fails

## See Also

- [FamilySearch API Documentation](https://developers.familysearch.org/)
- [Playwright Documentation](https://playwright.dev/python/)
- [OAuth2 Flow Documentation](./familysearch_oauth.md)
