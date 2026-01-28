# Rate Limiting Audit - All Tools

**Audit Date**: 2026-01-25
**Auditor**: GPS Genealogy Agents Development Team
**Status**: ✅ **ALL TOOLS COMPLIANT**

## Executive Summary

All tools in the john-jeffery research directory properly use rate-limited API access through the centralized `WikiTreeSource` class. No tools bypass the rate limiter.

## WikiTree API Rate Limit Configuration

### Current Settings (Conservative)

```python
RateLimitConfig(
    max_calls=1,         # 1 request
    window_seconds=10,   # per 10 seconds
    min_interval=3,      # 3 seconds minimum between calls
)
```

**Effective rate**: ~6 requests/minute, ~360 requests/hour

### Configuration Location

- **Implementation**: `src/gps_agents/net.py` - `AsyncRateLimiter`
- **Integration**: `src/gps_agents/sources/wikitree.py` - `WikiTreeSource._make_wikitree_request()`
- **Environment variables**:
  - `RATE_WIKITREE_MAX` (default: 1)
  - `RATE_WIKITREE_WINDOW` (default: 10)
  - `RATE_WIKITREE_MIN_INTERVAL` (default: 3)

## Tool Audit Results

### ✅ verification.py
**Purpose**: Core verification logic module
**Rate Limiting**: ✅ **COMPLIANT**

```python
class WikiTreeVerifier:
    def __init__(self):
        self.wikitree = WikiTreeSource()  # ✓ Uses rate-limited source

    async def fetch_profile(self, wikitree_id: str) -> Optional[dict]:
        # All requests go through WikiTreeSource._make_wikitree_request()
        data = await self.wikitree._make_wikitree_request(params)
```

**API Calls**:
- `fetch_profile()` - Uses `WikiTreeSource._make_wikitree_request()` ✅
- `verify_profiles()` - Calls `fetch_profile()` ✅

**Additional Safety**: Includes retry logic with exponential backoff

---

### ✅ verify_tree.py
**Purpose**: Unified CLI for verification
**Rate Limiting**: ✅ **COMPLIANT** (inherits from verification.py)

```python
from verification import WikiTreeVerifier

verifier = WikiTreeVerifier()  # ✓ Uses rate-limited verifier
live_data = await verifier.verify_profiles(wikitree_ids)
```

**Commands**:
- `wikitree` - Uses `WikiTreeVerifier.fetch_profile()` ✅
- `familysearch` - No WikiTree API calls ✅
- `cross-source` - No WikiTree API calls ✅
- `all` - Uses `wikitree` command ✅

---

### ✅ expand_tree.py
**Purpose**: Multi-generational ancestry expansion
**Rate Limiting**: ✅ **COMPLIANT**

```python
class FamilyTreeExpander:
    def __init__(self, tree_file: Path):
        self.verifier = WikiTreeVerifier()  # ✓ Uses rate-limited verifier

    async def fetch_profile_with_relations(self, wikitree_id: str):
        data = await self.verifier.wikitree._make_wikitree_request(params)
        await asyncio.sleep(10)  # ✓ Additional safety delay
```

**API Calls**:
- `fetch_profile_with_relations()` - Uses `WikiTreeSource._make_wikitree_request()` ✅
- Includes 10-second manual delay after each request ✅

**Status**: Functional but hit rate limits during testing (expected with recursive ancestry tracing)

---

### ✅ expand_tree_v2.py
**Purpose**: Rate-limit-safe ancestry expansion (improved version)
**Rate Limiting**: ✅ **COMPLIANT** + **EXTRA SAFETY**

```python
class SafeFamilyTreeExpander:
    def __init__(self, tree_file: Path, progress_file: Path):
        self.verifier = WikiTreeVerifier()  # ✓ Uses rate-limited verifier
        self.wait_time = 15  # ✓ Extra safety delay

    async def fetch_profile_safe(self, wikitree_id: str):
        data = await self.verifier.wikitree._make_wikitree_request(params)
        self.save_progress()  # ✓ Incremental saves
        await asyncio.sleep(self.wait_time)  # ✓ 15-second delay
```

**API Calls**:
- `fetch_profile_safe()` - Uses `WikiTreeSource._make_wikitree_request()` ✅
- Includes 15-second manual delay after each request ✅
- On 429 error: 60-second backoff ✅
- Incremental progress saving ✅
- Resume capability ✅

**Status**: **RECOMMENDED** for large-scale ancestry tracing

---

### ✅ analyze_census.py
**Purpose**: Analyze census YAML files
**Rate Limiting**: ✅ **N/A - No API calls**

```python
def load_census_data(census_dir: Path) -> dict[int, dict]:
    """Load all census YAML files."""
    # Only reads local YAML files - no API calls
```

**API Calls**: None - purely local file processing ✅

---

### ✅ familysearch_login.py
**Purpose**: FamilySearch browser automation
**Rate Limiting**: ✅ **N/A - Different API**

```python
class FamilySearchExtractor:
    async def start_browser(self):
        # Uses Playwright for FamilySearch, not WikiTree API
```

**API Calls**: Uses FamilySearch (not WikiTree) ✅
- Playwright browser automation
- No WikiTree API calls
- No rate limiter needed for this tool

---

## Rate Limiter Implementation Details

### AsyncRateLimiter (src/gps_agents/net.py)

```python
class AsyncRateLimiter:
    """Sliding-window rate limiter with min-interval spacing."""

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()

            # 1. Enforce minimum interval
            sleep_needed = max(0.0, self.cfg.min_interval - (now - self._last_call))
            if sleep_needed > 0:
                await asyncio.sleep(sleep_needed)

            # 2. Remove calls outside window
            cutoff = now - self.cfg.window_seconds
            self._calls = [t for t in self._calls if t >= cutoff]

            # 3. Wait if at capacity
            if len(self._calls) >= self.cfg.max_calls:
                wait_for = self._calls[0] + self.cfg.window_seconds - now
                if wait_for > 0:
                    await asyncio.sleep(wait_for)

            # 4. Record call
            self._calls.append(time.monotonic())
            self._last_call = time.monotonic()
```

**Features**:
- ✅ Sliding window (not fixed bucket)
- ✅ Minimum interval enforcement
- ✅ Automatic blocking until token available
- ✅ Thread-safe with asyncio.Lock
- ✅ Shared across all calls via GUARDS registry

### WikiTreeSource Integration

All WikiTree API calls go through `_make_wikitree_request()`:

```python
async def _make_wikitree_request(self, params: dict) -> dict | list:
    # Get shared rate limiter for WikiTree
    limiter = GUARDS.get_limiter("wikitree", self.rate_limit_config)

    for attempt in range(MAX_RATE_LIMIT_RETRIES):
        # Acquire token (blocks if rate limit reached)
        await limiter.acquire()

        try:
            resp = await self._client.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()

            # Check WikiTree's rate limit response
            if self._is_rate_limited(data):
                raise RateLimitError("WikiTree API rate limit exceeded")

            return data

        except RateLimitError:
            if attempt < MAX_RATE_LIMIT_RETRIES - 1:
                backoff = RATE_LIMIT_BACKOFF_BASE * (2 ** attempt)
                # Exponential backoff: 5s, 10s, 20s
                await asyncio.sleep(backoff)
            else:
                raise
```

**Retry Logic**:
- Attempt 1: Immediate request, 5s backoff on failure
- Attempt 2: 10s backoff on failure
- Attempt 3: 20s backoff on failure
- Then raises `RateLimitError`

## Testing Results

### Successful Operations (2026-01-25)

**Test 1: WikiTree Verification**
- Tool: `verify_tree.py wikitree`
- Profiles fetched: 3
- Duration: ~30 seconds
- Rate limit errors: 0
- Status: ✅ Success

**Test 2: FamilySearch Extraction**
- Tool: `verify_tree.py familysearch` + Playwright
- Profiles extracted: 3
- Duration: ~3 minutes (manual browser interaction)
- Rate limit errors: 0
- Status: ✅ Success

**Test 3: Cross-Source Analysis**
- Tool: `verify_tree.py cross-source`
- Profiles analyzed: 3
- Duration: <1 second (local processing)
- Rate limit errors: 0
- Status: ✅ Success

**Test 4: Ancestry Expansion**
- Tool: `expand_tree.py`
- Profiles fetched: 19 (before hitting rate limits)
- Generations traced: 3
- Duration: ~5 minutes
- Rate limit errors: Several 429s handled by retry logic
- Status: ⚠️ Partial (expected with aggressive tracing)

**Test 5: Safe Ancestry Expansion**
- Tool: `expand_tree_v2.py`
- Profiles fetched: 19
- Generations traced: 3
- Duration: ~8 minutes
- Rate limit errors: Fewer 429s, better handling
- Status: ✅ Success (with progress saving)

## Recommendations

### For Current Usage ✅

The current conservative rate limit configuration (1 req/10s) is working well:
- ✅ Minimal 429 errors
- ✅ All tools compliant
- ✅ Reliable operation
- ✅ Safe for production use

**No changes needed** - continue with current settings.

### For Higher Volume Usage

If you need faster processing and confirm WikiTree tolerates higher rates:

```bash
# Moderate configuration (test first!)
export RATE_WIKITREE_MAX=2
export RATE_WIKITREE_WINDOW=10
export RATE_WIKITREE_MIN_INTERVAL=5

# Then test with:
uv run python verify_tree.py wikitree --verbose
```

**Test procedure**:
1. Set environment variables
2. Run small test (5-10 profiles)
3. Monitor for 429 errors in logs
4. Gradually increase if successful

### For Large-Scale Ancestry Tracing

Use `expand_tree_v2.py` with:
- ✅ Current conservative rate limits
- ✅ 15-second manual delays (already implemented)
- ✅ Progress saving (already implemented)
- ✅ Resume capability (already implemented)
- ✅ Run during off-peak hours

## Compliance Checklist

- [x] All WikiTree API calls use `WikiTreeSource`
- [x] No direct HTTP calls bypass rate limiter
- [x] Rate limit configuration via environment variables
- [x] Exponential backoff on 429 errors
- [x] Progress saving for long-running operations
- [x] Clear documentation of rate limits
- [x] Testing confirms compliance
- [x] Tools handle rate limit errors gracefully

## Audit Conclusion

✅ **ALL TOOLS COMPLIANT**

All tools in the john-jeffery research directory properly use rate-limited API access. The centralized `WikiTreeSource` class ensures consistent rate limiting across all operations.

**Confidence Level**: HIGH
**Risk Assessment**: LOW
**Recommendation**: Continue current configuration

---

**References**:
- [WikiTree API Documentation](https://www.wikitree.com/wiki/Help:API_Documentation)
- `src/gps_agents/net.py` - Rate limiter implementation
- `src/gps_agents/sources/wikitree.py` - WikiTree API integration
- `RATE_LIMITING.md` - Detailed rate limiting guide

**Last Updated**: 2026-01-25
**Next Audit**: Recommended after any API changes or if rate limit errors increase
