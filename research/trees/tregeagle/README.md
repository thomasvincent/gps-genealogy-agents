# Tregeagle Family Research

Cornwall → New Zealand → American West (1837-1922)

## Files Created

### Data Files
- **`tregeagle_tree.json`** - Structured family tree (11 profiles)
- **`family_narrative.md`** - Detailed research narrative with sources
- **`multi_source_data.json`** - Validation results (created when validator runs)
- **`multi_source_cache.json`** - Cache to avoid re-fetching (created when validator runs)

### Scripts
- **`multi_source_validator.py`** - Automated multi-source validator

## Research Priorities

### HIGH PRIORITY (USA Lines)

#### James Eli Tregeagle (Utah)
- **Born:** c. 1870 (Cornwall or NZ)
- **Settled:** Provo, Utah
- **Status:** Well-known in Utah records
- **Needs:**
  - US Census 1900, 1910, 1920, 1930 (Provo)
  - Marriage record
  - Children's names
  - Death certificate

#### Sarah Georgina (Tregeagle) Gresty (Nevada)
- **Born:** c. 1863 (Cornwall)
- **Died:** 1922 (Silver City or Virginia City, Nevada)
- **Spouse:** Thomas Gresty
- **Needs:**
  - Immigration record
  - Marriage to Thomas Gresty
  - US Census 1900, 1910, 1920 (Nevada)
  - Death certificate (1922)
  - Cemetery record

## Multi-Source Validator

**Searches:**
- ✅ FindAGrave (free cemetery records)
- ✅ Chronicling America (Library of Congress newspapers)
- ✅ Archive.org (census references)
- ✅ State archives references (Utah, Nevada)

**Does NOT search:**
- ❌ FamilySearch (per user request)

### Running the Validator

```bash
cd /Users/thomasvincent/Developer/github.com/thomasvincent/gps-genealogy-agents/research/trees/tregeagle
uv run python multi_source_validator.py
```

**Features:**
- Human-like pacing (5-12 second delays)
- Breaks every 10 profiles (60-120 seconds)
- Aggressive caching (never re-fetches)
- Prioritizes HIGH research_priority profiles first
- Saves progress after each profile

**Output:**
- `multi_source_data.json` - All discovered records
- `multi_source_cache.json` - Cached results
- `multi_source_progress.json` - Resume checkpoint

## Sources

### Primary Information
- **Source:** Quenton Tregeagle (family historian)
- **Confirmed:** Marriage (1862), *Waitangi* voyage (1876), Death (1880)

### Public Databases
1. **FindAGrave.com** - Cemetery records
2. **ChroniclingAmerica.loc.gov** - Historical newspapers (1836-1963)
3. **Archive.org** - Digitized census and historical records
4. **Utah State Archives** - archives.utah.gov
5. **Nevada State Archives** - nvculture.org/nsla

## Research Timeline

### Confirmed Events
- **1837** - James Tregeagle born (Cornwall)
- **1862-07-20** - James & Rosina married (Kenwyn, Cornwall)
- **1863-1880** - Nine children born (Cornwall/NZ)
- **1876** - Family emigrates aboard *Waitangi* to Canterbury, NZ
- **1880-12-28** - James dies (Auckland, age 43, fell from barn)
- **1890s-1900s** - James Eli moves to Utah, Sarah to Nevada
- **1922** - Sarah Georgina dies (Nevada)

### Research Gaps
- Exact immigration dates (James Eli & Sarah to USA)
- Marriage details (Sarah to Thomas Gresty)
- Children of James Eli (Utah line)
- Census records (USA, 1900-1930)
- Death records (James Eli, Rosina)
- Details on remaining 7 children

## Next Steps

1. **Run multi-source validator** for automated searches
2. **Manual research** for state archives (Utah, Nevada)
3. **WikiTree profiles** for confirmed family members
4. **DNA testing** to confirm USA descendants
5. **Local archives** (Provo, Virginia City libraries)

## Notes

- Several children died young (era-appropriate)
- Tregeagle = Cornish "settlement of geese" (or "throat")
- Mining connection (Cornwall → NZ → Nevada)
- Mormon settlement pattern (Utah)
- Comstock Lode era (Nevada silver boom)

---

*Last updated: 2026-01-27*
