# Family Tree Verification CLI

Unified tool for verifying family tree data across WikiTree and FamilySearch, assessing GPS Pillar 3 compliance.

## Quick Start

```bash
# Verify WikiTree profiles are current
uv run python verify_tree.py wikitree

# Extract FamilySearch data
uv run python verify_tree.py familysearch

# Analyze cross-source corroboration
uv run python verify_tree.py cross-source

# Run everything
uv run python verify_tree.py all
```

## Commands

### `wikitree` - Verify WikiTree Profiles

Fetches live data from WikiTree API and compares with cached tree.json.

```bash
uv run python verify_tree.py wikitree [OPTIONS]

Options:
  --tree, -t PATH       Path to tree.json
  --output, -o PATH     Output JSON file
  --verbose, -v         Detailed output
```

**Output**: `wikitree_verification.json`

**GPS Impact**: Verifies source currency

---

### `familysearch` - Extract FamilySearch Data

Searches FamilySearch and extracts family relationships using Playwright.

```bash
uv run python verify_tree.py familysearch [OPTIONS]

Options:
  --tree, -t PATH       Path to tree.json
  --output, -o PATH     Output JSON file
```

**Output**: `familysearch_extraction.json` (search URLs + extraction data)

**GPS Impact**: Provides second independent source

---

### `cross-source` - Analyze GPS Compliance

Compares WikiTree vs FamilySearch to assess cross-source corroboration.

```bash
uv run python verify_tree.py cross-source [OPTIONS]

Options:
  --wikitree PATH       WikiTree verification JSON
  --familysearch PATH   FamilySearch extraction JSON
  --output, -o PATH     Output JSON file
```

**Output**: `cross_source_analysis.json`

**GPS Grading**:
- **Compliant**: ≥80% relationships confirmed by 2+ sources
- **Partial**: 50-79% confirmed
- **Incomplete**: <50% confirmed or single-source only

---

### `all` - Complete Suite

Runs all verification steps in sequence.

```bash
uv run python verify_tree.py all --tree tree.json --verbose
```

## Architecture

### DRY Design - No Duplication

All logic consolidated in `verification.py`:
- `TreeData` - Loads tree.json
- `WikiTreeVerifier` - Fetches live WikiTree data
- `FamilySearchVerifier` - Extracts FamilySearch data (Playwright)
- `CrossSourceAnalyzer` - Compares sources

Old duplicate scripts removed:
- ~~verify_family_tree.py~~
- ~~verify_live_trees.py~~
- ~~verify_familysearch_tree.py~~
- ~~fetch_familysearch_census.py~~

## Playwright Integration

The `familysearch` command uses Playwright for browser automation. Search URLs are generated, ready for MCP tool integration.

Example Playwright code:
```javascript
async (page) => {
    await page.goto('https://www.familysearch.org/search/...');
    const firstResult = await page.locator('a.person-name').first();
    await firstResult.click();
    const family = await page.locator('[data-test="family-members"]').textContent();
    return { family_text: family };
}
```

## GPS Pillar 3 Assessment

### What is GPS Pillar 3?

**Analysis & Correlation** requires:
1. ✓ Exhaustive search (WikiTree + FamilySearch)
2. ✓ Accurate citations (WikiTree IDs, FS collections)
3. ⚠️ **Correlation across independent sources** (what this tool measures)

### Compliance Levels

| Grade | Status | Requirement |
|-------|--------|-------------|
| Compliant | ✓ Strong | ≥80% confirmed by 2+ sources |
| Partial | ⚠️ Moderate | 50-79% confirmed |
| Incomplete | ❌ Weak | <50% confirmed |

## Current Status (John Jeffery Research)

### WikiTree (Verified Live ✓)

3 profiles, all up-to-date as of 2026-01-25:
- John Jeffery (Jeffery-538)
- John Jefferies (Jefferies-795)
- Joseph Jeffcoat (Jeffcoat-237)

### FamilySearch (Search URLs Generated)

5 collection references:
- England Marriages 1826
- England Census 1841, 1851, 1861
- Michigan Deaths 1899

### GPS Compliance: ❌ INCOMPLETE

All 6 family relationships are single-source (WikiTree only).

**Next**: Extract FamilySearch person profiles or census household data for corroboration.

## Example Workflow

```bash
# 1. Verify WikiTree
uv run python verify_tree.py wikitree
# → wikitree_verification.json

# 2. Extract FamilySearch (generates search URLs)
uv run python verify_tree.py familysearch
# → familysearch_extraction.json

# 3. Manually extract FamilySearch data or use Playwright automation

# 4. Assess GPS compliance
uv run python verify_tree.py cross-source
# → cross_source_analysis.json
# → GPS Pillar 3 grade: Compliant/Partial/Incomplete
```

## Generated Reports

- `wikitree_verification.json` - Live WikiTree data + comparison
- `familysearch_extraction.json` - Search URLs + extracted relationships
- `cross_source_analysis.json` - GPS Pillar 3 assessment

## Troubleshooting

**Rate Limiting (429)**:
- WikiTree: 1 req/10s limit
- Wait a few minutes before retrying

**Missing Dependencies**:
```bash
uv sync
uv pip install typer rich
```

**Playwright**:
```bash
playwright install chromium
```

## Related Files

- `analyze_census.py` - Census data analysis
- `census_*.yaml` - Census extraction templates
- `VERIFICATION_SUMMARY.md` - Detailed verification summary
- `README.md` - Census extraction guide

---

Part of GPS Genealogy Agents - MIT License
