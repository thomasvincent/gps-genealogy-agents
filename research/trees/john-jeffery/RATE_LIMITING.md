# WikiTree API Rate Limiting Configuration

## Official Rate Limits

**WikiTree API does not publicly document specific rate limits**, but based on:
- Community discussions ([G2G Forum](https://www.wikitree.com/g2g/1641925/what-does-status-limit-exceeded-mean))
- [API Documentation](https://www.wikitree.com/wiki/Help:API_Documentation)
- Practical testing and 429 error responses

### Observed Limits (Conservative Estimates)

WikiTree implements rate limiting per IP address/user with:
- **Unauthenticated requests**: Stricter limits
- **With appId parameter**: More lenient limits
- **429 "Limit exceeded"**: When threshold is reached

### Current Implementation

Our codebase uses the **AsyncRateLimiter** from `gps_agents/net.py` with:

```python
RateLimitConfig(
    max_calls=1,        # Maximum requests
    window_seconds=10,   # Per time window
    min_interval=3,      # Minimum seconds between requests
)
```

**Default behavior**: 1 request per 10 seconds with 3-second spacing
- **Effective rate**: ~6 requests per minute
- **Hourly maximum**: ~360 requests per hour
- **Very conservative** to avoid any rate limit errors

## Configuration via Environment Variables

You can adjust rate limits using environment variables:

```bash
# Maximum requests per window
export RATE_WIKITREE_MAX=2

# Window size in seconds
export RATE_WIKITREE_WINDOW=10

# Minimum interval between requests (seconds)
export RATE_WIKITREE_MIN_INTERVAL=5
```

### Recommended Configurations

#### Ultra-Safe (Default)
```bash
export RATE_WIKITREE_MAX=1
export RATE_WIKITREE_WINDOW=10
export RATE_WIKITREE_MIN_INTERVAL=3
```
- **Rate**: 6 requests/minute, 360 requests/hour
- **Use case**: Initial testing, unknown limits

#### Conservative (Recommended)
```bash
export RATE_WIKITREE_MAX=2
export RATE_WIKITREE_WINDOW=10
export RATE_WIKITREE_MIN_INTERVAL=5
```
- **Rate**: 12 requests/minute, 720 requests/hour
- **Use case**: General usage with safety margin

#### Moderate (If limits are higher)
```bash
export RATE_WIKITREE_MAX=3
export RATE_WIKITREE_WINDOW=10
export RATE_WIKITREE_MIN_INTERVAL=3
```
- **Rate**: 18 requests/minute, 1080 requests/hour
- **Use case**: After confirming higher limits work

## How Rate Limiting Works

### AsyncRateLimiter Implementation

Located in `src/gps_agents/net.py`:

```python
class AsyncRateLimiter:
    """Sliding-window rate limiter with min-interval spacing."""

    async def acquire(self) -> None:
        # 1. Enforce minimum interval between calls
        sleep_needed = max(0.0, min_interval - (now - last_call))

        # 2. Remove calls outside the window
        cutoff = now - window_seconds
        calls = [t for t in calls if t >= cutoff]

        # 3. If at capacity, wait until oldest call expires
        if len(calls) >= max_calls:
            wait_for = calls[0] + window_seconds - now
            await asyncio.sleep(wait_for)

        # 4. Record this call
        calls.append(now)
```

**Features**:
- ✅ **Sliding window**: More accurate than fixed windows
- ✅ **Min interval enforcement**: Prevents burst requests
- ✅ **Automatic waiting**: Blocks until token available
- ✅ **Thread-safe**: Uses asyncio.Lock

### Automatic Retry with Exponential Backoff

WikiTreeSource (`src/gps_agents/sources/wikitree.py`) also implements:

```python
MAX_RATE_LIMIT_RETRIES = 3
RATE_LIMIT_BACKOFF_BASE = 5.0  # seconds

for attempt in range(MAX_RATE_LIMIT_RETRIES):
    try:
        # Make request...
    except RateLimitError:
        backoff = RATE_LIMIT_BACKOFF_BASE * (2 ** attempt)
        # Wait: 5s, 10s, 20s
        await asyncio.sleep(backoff)
```

**Retry schedule** (on 429 error):
- Attempt 1: Wait 5 seconds
- Attempt 2: Wait 10 seconds
- Attempt 3: Wait 20 seconds
- Then raise RateLimitError

## Verification CLI Tools

### Already Rate-Limited ✅

All these tools use `WikiTreeSource` and benefit from rate limiting:

1. **`verify_tree.py wikitree`**
   - Fetches live WikiTree profiles
   - Uses: `WikiTreeVerifier.fetch_profile()`
   - Rate limited: ✅

2. **`verify_tree.py all`**
   - Runs complete verification suite
   - Rate limited: ✅

3. **`expand_tree_v2.py`**
   - Traces multi-generational ancestry
   - Uses: `WikiTreeSource._make_wikitree_request()`
   - Rate limited: ✅
   - Additional: 15-second manual wait between profiles

### Manual Waiting (Extra Safety)

`expand_tree_v2.py` adds extra protection:

```python
# After each successful API call
await asyncio.sleep(15)  # Extra 15-second wait

# On 429 error
await asyncio.sleep(60)  # 60-second backoff
```

This is **in addition** to the automatic rate limiter, providing double protection.

## Rate Limit Best Practices

### 1. Always Use WikiTreeSource

✅ **Correct** (automatic rate limiting):
```python
from gps_agents.sources.wikitree import WikiTreeSource

wikitree = WikiTreeSource()
data = await wikitree._make_wikitree_request(params)
```

❌ **Incorrect** (bypasses rate limiter):
```python
import httpx
client = httpx.AsyncClient()
resp = await client.get("https://api.wikitree.com/api.php", params=params)
```

### 2. Batch Requests When Possible

Use `getPeople` instead of multiple `getPerson` calls:

```python
# ✅ One request for multiple profiles
params = {
    "action": "getPeople",
    "keys": "Jeffery-538,Jefferies-795,Jeffcoat-237",
    ...
}
```

### 3. Include appId Parameter

Always include an app identifier:

```python
params = {
    "action": "getPerson",
    "appId": "gps-genealogy-agents",  # Identifies your app
    ...
}
```

This may grant more lenient rate limits.

### 4. Monitor Rate Limit Status

Check current limiter state:

```python
from gps_agents.net import report_status

status = report_status()
print(status["wikitree"])
# {
#   "circuit_open": False,
#   "rate": {
#     "max_calls": 1,
#     "window_seconds": 10,
#     "min_interval": 3
#   }
# }
```

## Handling Rate Limit Errors

### Error Types

1. **HTTP 429** - Server returns "Too Many Requests"
   - Automatic exponential backoff
   - Retries up to 3 times

2. **WikiTree Status Response** - `{"status": "Limit exceeded."}`
   - Detected by `_is_rate_limited()`
   - Raised as `RateLimitError`
   - Same retry logic as HTTP 429

### Error Handling in Scripts

```python
from gps_agents.sources.wikitree import WikiTreeSource, RateLimitError

wikitree = WikiTreeSource()

try:
    data = await wikitree._make_wikitree_request(params)
except RateLimitError:
    # Rate limit exceeded after all retries
    print("Rate limited! Try again later.")
    # Save progress and exit gracefully
except Exception as e:
    print(f"Other error: {e}")
```

## Testing Rate Limits

### Safe Testing Procedure

1. **Start with ultra-safe defaults** (current configuration)
2. **Run small test**: Fetch 5-10 profiles
3. **Monitor for 429 errors**
4. **Gradually increase** if no errors
5. **Log all rate limit hits**

### Test Script

```python
import asyncio
from gps_agents.sources.wikitree import WikiTreeSource

async def test_rate_limit():
    wikitree = WikiTreeSource()

    # Test with 20 requests
    test_ids = ["Jeffery-538"] * 20

    for i, wt_id in enumerate(test_ids, 1):
        print(f"Request {i}/20...")
        try:
            params = {
                "action": "getPerson",
                "key": wt_id,
                "format": "json"
            }
            data = await wikitree._make_wikitree_request(params)
            print(f"  ✓ Success")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            break

asyncio.run(test_rate_limit())
```

## Current Status

### Verified Working Configuration

As of 2026-01-25, the default configuration **successfully** traced:
- **19 profiles** across 3 generations
- **0 permanent failures** (some 429s handled by retry)
- **Total time**: ~5 minutes

### Encountered Issues

During ancestry expansion, we hit rate limits with:
- Multiple rapid successive requests
- **Root cause**: Script was fetching parents recursively without enough delay
- **Solution**: Added 15-second manual wait between profiles in `expand_tree_v2.py`

## Recommendations

### For New Projects

1. **Start with default conservative settings**
2. **Add progress saving** (for long-running tasks)
3. **Add manual delays** for extra safety (10-15 seconds)
4. **Monitor logs** for rate limit errors

### For Production Use

1. **Implement queue-based processing** for large batches
2. **Add retry logic** with exponential backoff
3. **Cache aggressively** to minimize API calls
4. **Use batch endpoints** (`getPeople`) when possible

## Sources

- [WikiTree API Documentation](https://www.wikitree.com/wiki/Help:API_Documentation)
- [WikiTree G2G Forum - Rate Limits](https://www.wikitree.com/g2g/1641925/what-does-status-limit-exceeded-mean)
- [WikiTree GitHub - API Examples](https://github.com/wikitree/wikitree-api)
- [WikiTree App Policies](https://www.wikitree.com/wiki/Help:App_Policies)

---

**Last Updated**: 2026-01-25
**Tested Configuration**: 1 req/10s, 3s min interval
**Status**: ✅ Working reliably
