# Ancestry Expansion Plan

## Current Status (2026-01-25)

### GPS Pillar 3: ✅ COMPLIANT (100%)

Successfully achieved full GPS Pillar 3 compliance with cross-source verification:
- **6 of 6 relationships** confirmed by multiple independent sources
- WikiTree + FamilySearch christening records
- All naming conflicts resolved (maiden vs. married names)

### Profiles Verified

1. **John Jeffery** (Jeffery-538)
   - Born: 1803-04-03, Brenchley, Kent, England
   - Father: Edward Jeffery (Jeffery-390)
   - Mother: Lydia Hickmott (Hickmott-289)

2. **John Jefferies** (Jefferies-795)
   - Born: 1803-08-07, Forncett St Mary, Norfolk, England
   - Father: John Jefferies (Jefferies-721)
   - Mother: Mary Hubbard (Hubbard-7253)

3. **Joseph Jeffcoat** (Jeffcoat-237)
   - Born: 1803-10-19, Aylesbury, Buckinghamshire, England
   - Father: John Jeffcoat (Jeffcoat-234)
   - Mother: Rebecca Fardon (Fardon-19)

## Expansion Plan

### Phase 1: Siblings (Pending)

Extract siblings for each of the three primary profiles using WikiTree API:
- `getSiblings=1` parameter
- Include half-siblings
- Cross-reference with FamilySearch for verification

### Phase 2: Multi-Generational Ancestry (In Progress)

**Target**: Trace ancestry back 5-10 generations (approximately 1650-1750)

**Known Ancestry from WikiTree Data**:

#### John Jeffery Line (Jeffery-538)
```
Generation 1 (1803):
├─ John Jeffery (Jeffery-538)

Generation 2 (1765-1773):
├─ Father: Edward Jeffery (Jeffery-390)
│  ├─ Born: 1765-12-29, Lamberhurst, Kent
│  ├─ Died: 1849-06-03, Brenchley, Kent
│  ├─ Father: Jeffery-1237 (ID: 15664277) ← Gen 3
│  └─ Mother: Baldwin-8616 (ID: 15664289) ← Gen 3
└─ Mother: Lydia Hickmott (Hickmott-289)
   ├─ Born: 1773-05-09, Lamberhurst, Kent
   ├─ Died: 1808-00-00, Brenchley, Kent
   ├─ Father: Hickmott-283 (ID: 7958533) ← Gen 3
   └─ Mother: Avery-5760 (ID: 21857332) ← Gen 3
```

#### John Jefferies Line (Jefferies-795)
```
Generation 1 (1803):
├─ John Jefferies (Jefferies-795)

Generation 2 (1780-1781):
├─ Father: John Jefferies (Jefferies-721)
│  ├─ Born: 1780-03-19, Pulham, Norfolk
│  ├─ Father: Jefferies-887 (ID: 29214049) ← Gen 3
│  └─ Mother: Thorold-88 (ID: 29214553) ← Gen 3
└─ Mother: Mary Hubbard (Hubbard-7253)
   ├─ Born: 1781-04-08, Tivetshall St Margaret, Norfolk
   ├─ Father: Hubbard-7254 (ID: 23957193) ← Gen 3
   └─ Mother: Gardiner-4482 (ID: 29213432) ← Gen 3
```

#### Joseph Jeffcoat Line (Jeffcoat-237)
```
Generation 1 (1803):
├─ Joseph Jeffcoat (Jeffcoat-237)

Generation 2 (1776):
├─ Father: John Jeffcoat (Jeffcoat-234)
│  ├─ Born: 1776-03-15, Upper Winchendon, Buckinghamshire
│  ├─ Died: 1840-00-00, Kankakee, Illinois, USA
│  ├─ Father: Jeffcoat-235 (ID: 22170498) ← Gen 3
│  └─ Mother: Eaton-6418 (ID: 22170506) ← Gen 3
└─ Mother: Rebecca Fardon (Fardon-19)
   ├─ Born: 1776-05-28, Sibford Ferris, Oxfordshire
   ├─ Died: 1838-00-00, Crawford, Illinois, USA
   ├─ Father: Fardon-20 (ID: 22177979) ← Gen 3
   └─ Mother: Harris-34530 (ID: 22178004) ← Gen 3
```

### Phase 3: FamilySearch Corroboration

For each ancestor discovered:
1. Search FamilySearch for birth/christening records
2. Extract parent names from parish registers
3. Cross-reference with WikiTree data
4. Maintain GPS Pillar 3 compliance throughout

## Rate Limiting Strategy

**WikiTree API Limits**:
- Default: 10 requests per 10 seconds
- Enhanced: May be higher for some accounts
- 429 errors require 60+ second backoff

**Safe Expansion Script** (`expand_tree_v2.py`):
- 15-second wait between requests
- Automatic 60-second backoff on 429 errors
- Incremental progress saving
- Resume capability
- Max 5 generations per run to limit API usage

## Next Steps

1. ✅ **Completed**: GPS Pillar 3 COMPLIANT status achieved
2. ⏳ **In Progress**: Multi-generational ancestry tracing (paused due to rate limits)
3. ⏰ **Pending**: Wait 60+ minutes for WikiTree rate limit reset
4. 📋 **Next Run**: Execute `expand_tree_v2.py` to continue tracing
5. 🎯 **Goal**: Complete ancestry back to 1650-1750 with FamilySearch verification

## Tools Created

### Unified Verification CLI (`verify_tree.py`)
- `wikitree` - Live WikiTree verification
- `familysearch` - FamilySearch extraction via Playwright
- `cross-source` - GPS Pillar 3 analysis
- `all` - Complete verification suite

### Safe Expansion Script (`expand_tree_v2.py`)
- Rate-limit-safe ancestry tracing
- Incremental progress saving
- Automatic resume on interruption
- Siblings + multi-generational parents

## Expected Output

### Siblings
- All siblings of John Jeffery, John Jefferies, and Joseph Jeffcoat
- Birth/death dates and locations
- Cross-verified with FamilySearch when possible

### Ancestry (5+ Generations)
- **Generation 1**: 3 people (1803)
- **Generation 2**: 6 people (1760s-1780s)
- **Generation 3**: 12 people (1730s-1750s)
- **Generation 4**: 24 people (1700s-1720s)
- **Generation 5**: 48 people (1670s-1690s)
- **Total**: ~90+ ancestors traced

## GPS Compliance Maintenance

As we expand the tree:
- Each new generation requires independent source verification
- FamilySearch parish registers provide primary source corroboration
- Maintain ≥80% multi-source confirmation for GPS Pillar 3
- Document conflicts and resolution decisions

## Files Generated

- `expanded_tree.json` - Complete ancestry structure
- `expansion_progress.json` - Incremental progress (resume capability)
- `familysearch_expanded_ancestry.json` - FamilySearch records for all ancestors
- `ancestry_verification_report.json` - GPS compliance for entire tree

## Timeline Estimate

**With Rate Limiting**:
- ~15 seconds per profile
- ~90 profiles target
- ~22.5 minutes of API calls
- Spread across 2-3 hours due to rate limits

**Realistic**: 1-2 days for complete ancestry tracing with verification
