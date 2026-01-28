# FamilySearch API Authentication Setup

## Why Do This?

Instead of manually copying census data, you can authenticate with FamilySearch and let the tool automatically fetch:
- Full census transcriptions
- Original record details
- Image URLs
- Complete citations

## Prerequisites

- FamilySearch account (free at https://www.familysearch.org)
- Developer API credentials (free)

---

## Step 1: Register for FamilySearch API Access

### 1.1 Go to FamilySearch Developer Portal
Visit: https://www.familysearch.org/developers/

### 1.2 Sign In
Use your regular FamilySearch account credentials.

### 1.3 Register Your Application
1. Click **"My Apps"** or **"Register an App"**
2. Fill in:
   - **App Name**: "GPS Genealogy Research" (or your choice)
   - **Redirect URI**: `http://localhost:8080/callback`
   - **Description**: "Personal genealogy research using GPS standards"
   - **App Type**: Select "Native App" or "Web App"

3. Click **"Register"** or **"Create"**

### 1.4 Get Your Credentials
After registration, you'll receive:
- **Client ID** (also called "App Key") - looks like: `a1b2-c3d4-e5f6-g7h8`
- **Client Secret** (optional, depends on app type)

**⚠️ IMPORTANT:** Keep these secret! Don't share or commit to git.

---

## Step 2: Configure Environment Variables

### 2.1 Open/Create `.env` File
```bash
cd /Users/thomasvincent/Developer/github.com/thomasvincent/gps-genealogy-agents
nano .env
```

### 2.2 Add FamilySearch Credentials
Add these lines (replace with your actual credentials):

```bash
# FamilySearch API Authentication
FAMILYSEARCH_CLIENT_ID="your-client-id-here"
FAMILYSEARCH_CLIENT_SECRET="your-client-secret-here"  # If required

# Example:
# FAMILYSEARCH_CLIENT_ID="a1b2-c3d4-e5f6-g7h8"
# FAMILYSEARCH_CLIENT_SECRET="secret123"
```

### 2.3 Verify Configuration
```bash
uv run python -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('Client ID:', os.getenv('FAMILYSEARCH_CLIENT_ID', 'NOT SET'))
print('Client Secret:', os.getenv('FAMILYSEARCH_CLIENT_SECRET', 'NOT SET'))
"
```

Should output your credentials (not "NOT SET").

---

## Step 3: Authenticate with FamilySearch

### 3.1 Run OAuth Authentication

The system uses OAuth2 - you'll authenticate once in a browser, then the tool can access your FamilySearch data.

```bash
uv run python -m gps_agents.sources.familysearch_client --authenticate
```

This will:
1. Open your browser
2. Prompt you to sign in to FamilySearch
3. Ask permission to access your data
4. Redirect back with authentication token
5. Save token for future use

### 3.2 Alternative: Check if Source is Available

```bash
uv run gps-agents research "Test FamilySearch connection"
```

If it prompts for authentication, follow the browser flow.

---

## Step 4: Verify Authentication Works

### Test Search
```bash
uv run python << 'EOF'
import asyncio
from gps_agents.sources.familysearch_client import FamilySearchClient

async def test():
    client = FamilySearchClient()

    # Test authentication
    if await client.authenticate():
        print("✓ Authentication successful!")

        # Test search
        results = await client.search_person(
            given_name="John",
            surname="Jeffery",
            birth_year=1803
        )

        print(f"✓ Found {len(results)} results")
        for r in results[:3]:
            print(f"  - {r.get('name')} ({r.get('birth_year')})")
    else:
        print("✗ Authentication failed")

asyncio.run(test())
EOF
```

Expected output:
```
✓ Authentication successful!
✓ Found 15 results
  - John Jeffery (1803)
  - John Jeffery (1803)
  - John Jeffery (1805)
```

---

## Step 5: Use Automated Census Fetching

### Option A: Fetch Census with Record URL

If you have the FamilySearch record URL/ARK:

```bash
uv run python << 'EOF'
import asyncio
from gps_agents.sources.familysearch_client import FamilySearchClient

async def fetch_census():
    client = FamilySearchClient()

    # Replace with your actual FamilySearch ARK/URL
    record_url = "https://www.familysearch.org/ark:/61903/1:1:XXXX-XXX"

    record = await client.fetch_record(record_url)

    print("Name:", record.get('name'))
    print("Age:", record.get('age'))
    print("Birthplace:", record.get('birthplace'))
    print("Household:", record.get('household'))

asyncio.run(fetch_census())
EOF
```

### Option B: Re-run Automated Search with Auth

Now that you're authenticated, re-run the crawl:

```bash
uv run gps-agents crawl person \
  --given "John" \
  --surname "Jeffery" \
  --birth-year 1803 \
  --birth-place "England" \
  --tree-out "research/trees/john-jeffery/tree_authenticated.json" \
  --max-iterations 100 \
  --verbose
```

With authentication, the FamilySearch source will:
- Fetch full census transcriptions (not just metadata)
- Include household members
- Include detailed birthplaces
- Include image URLs

---

## Step 6: Auto-Generate Census YAML Files

### Create Script to Convert FamilySearch Data to YAML

```bash
uv run python research/trees/john-jeffery/import_from_familysearch.py
```

This script will:
1. Read authenticated FamilySearch census records from tree.json
2. Extract detailed census information
3. Auto-populate census_YEAR.yaml files
4. You just review and confirm

---

## Troubleshooting

### Error: "Invalid Client ID"
- Double-check `.env` file has correct `FAMILYSEARCH_CLIENT_ID`
- Verify no extra spaces or quotes
- Make sure you copied the entire ID from developer portal

### Error: "Authentication Failed"
- Check redirect URI matches: `http://localhost:8080/callback`
- Try logging out of FamilySearch website, then re-authenticate
- Clear browser cookies for familysearch.org

### Error: "Access Denied"
- FamilySearch account must be in good standing
- Some records require LDS account (church membership)
- Try searching for publicly available records first

### Browser Doesn't Open
- Manually copy the URL from terminal
- Paste into browser
- Complete authentication
- Copy the callback URL back to terminal

### Records Still Empty
- FamilySearch API may not have full transcriptions for all records
- Some census images don't have indexed data
- You may still need manual extraction for detailed info

---

## Privacy & Security

### What Access Does the Tool Get?

The OAuth token allows:
- ✅ Read your family tree
- ✅ Read records you've attached
- ✅ Search public records
- ❌ **Cannot** modify your tree
- ❌ **Cannot** access private records without permission

### Token Storage

Tokens are stored locally:
- Location: `~/.config/gps-agents/familysearch_token.json`
- Not uploaded to any server
- Only valid for your account

### Revoking Access

To revoke access:
1. Go to https://www.familysearch.org/developers/
2. Click "My Apps"
3. Find your app
4. Click "Revoke Token" or delete the app

Or delete local token:
```bash
rm ~/.config/gps-agents/familysearch_token.json
```

---

## What This Enables

With FamilySearch authentication:

| Without Auth | With Auth |
|--------------|-----------|
| Manual census extraction | Automatic census fetching |
| Copy/paste from images | Direct API data |
| Limited to visible records | Access to all your attached sources |
| ~30 min per census | ~30 seconds for all censuses |

---

## Next Steps After Setup

Once authenticated:

1. **Re-run the crawl** with authentication enabled
2. **Check tree.json** for detailed census data
3. **Run import script** to auto-populate YAML files
4. **Review and verify** auto-generated data
5. **Run analysis** as usual

---

## Alternative: Manual Entry (If API Doesn't Work)

If you can't get API access or authentication fails:
- **Fallback to manual YAML entry** (the templates are still there)
- FamilySearch API is optional, not required
- Manual entry ensures you understand the data

---

## Questions?

- **FamilySearch API docs**: https://www.familysearch.org/developers/docs/api/
- **Developer forum**: https://community.familysearch.org/en/group/160-api
- **OAuth guide**: https://www.familysearch.org/developers/docs/guides/authentication
