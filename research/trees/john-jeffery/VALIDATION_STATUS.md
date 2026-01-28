# Ancestry Validation Status

**Generated**: 2026-01-26
**Total Profiles**: 32
**Requiring Validation**: 29
**Already Validated**: 3 (Jeffery-538, Jefferies-795, Jeffcoat-237)

## Validation Goal

Achieve GPS (Genealogical Proof Standard) Pillar 3 COMPLIANT status for all 32 ancestors by cross-verifying WikiTree data with primary sources (FamilySearch parish registers).

## Current Status

### ✅ Already Validated (GPS COMPLIANT)

1. **John Jeffery** (Jeffery-538) - Christening record verified ✅
2. **John Jefferies** (Jefferies-795) - Christening record verified ✅
3. **Joseph Jeffcoat** (Jeffcoat-237) - Christening record verified ✅

All 6 parent relationships confirmed by FamilySearch christening records.

### ⏳ Requiring Validation (29 profiles)

#### Generation 2 (Parents) - 6 profiles
1. Edward Jeffery (Jeffery-390) - b. 1765 Lamberhurst, Kent
2. Lydia Hickmott (Hickmott-289) - b. 1773 Lamberhurst, Kent
3. John Jefferies (Jefferies-721) - b. 1780 Pulham, Norfolk
4. Mary Hubbard (Hubbard-7253) - b. 1781 Tivetshall, Norfolk
5. John Jeffcoat (Jeffcoat-234) - b. 1776 Upper Winchendon, Bucks
6. Rebecca Fardon (Fardon-19) - b. 1776 Sibford Ferris, Oxfordshire

#### Generation 3 (Grandparents) - 12 profiles
7. Thomas Jeffery (Jeffery-1237) - b. 1735 Horsmonden, Kent
8. Rachel Baldwin (Baldwin-8616) - b. 1741 Lamberhurst, Kent
9. John Hickmott (Hickmott-283) - b. 1740 Lamberhurst, Kent
10. Martha Avery (Avery-5760) - b. Unknown
11. William Jefferies (Jefferies-887) - b. Unknown
12. Elizabeth Thorold (Thorold-88) - b. Unknown
13. Samuel Hubbard (Hubbard-7254) - b. Unknown
14. Elizabeth Gardiner (Gardiner-4482) - b. Unknown
15. Marmaduke Jeffcoat (Jeffcoat-235) - b. Unknown
16. Anne Eaton (Eaton-6418) - b. Unknown
17. Benjamin Fardon (Fardon-20) - b. Unknown
18. Rebecca Harris (Harris-34530) - b. Unknown

#### Generation 4+ (Great-grandparents and beyond) - 11 profiles
19. George Hickmott (Hickmott-290) - b. 1716 Horsmonden, Kent
20. Unknown-238808 - b. 1721 Lamberhurst, Kent
21. John Avery (Avery-5821) - b. Unknown
22. John Jefferies (Jefferies-881) - b. Unknown
23. Mary Kybird (Kybird-2) - b. Unknown
24. Samuel Hubbard (Hubbard-8642) - b. Unknown
25. Mary Clayton (Clayton-6804) - b. Unknown
26. Richard Hickmott (Hickmott-299) - b. 1684 Horsmonden, Kent
27. Susanna Russell (Russell-7272) - b. 1698 Horsmonden, Kent
28. John Avery (Avery-9713) - b. 1647 Sussex ⭐ EARLIEST
29. Elizabeth Aynscombe (Aynscombe-10) - b. Unknown

## Validation Methodology

### Primary Sources (Preferred)
1. **Christening Records** - Parish registers from FamilySearch
2. **Birth Records** - Civil registration (post-1837)
3. **Census Records** - As corroborating evidence

### Validation Criteria
For each profile, we need:
- ✅ Birth/christening date confirmation
- ✅ Birth/christening location confirmation
- ✅ Parents' names confirmation
- ✅ Source citation from FamilySearch

### GPS Pillar 3 Target
- **Goal**: ≥80% of 29 profiles confirmed by primary sources
- **Minimum**: 24 of 29 profiles validated
- **Current**: 3 of 32 profiles validated (9%)

## Validation Approach

### Option 1: Automated Playwright Extraction (Recommended)
- Use existing `familysearch_login.py` automation
- Process profiles in batches of 10
- Extract christening records automatically
- Estimated time: 2-3 hours for all 29 profiles

### Option 2: Manual Search with Pre-generated URLs
- Use `ancestry_validation_plan.json` with FamilySearch URLs
- Manually search each profile
- Copy/paste record data
- Estimated time: 4-5 hours for all 29 profiles

### Option 3: Prioritized Validation
- **Priority 1**: Gen 2 (6 profiles) - Direct parents
- **Priority 2**: Gen 3 (12 profiles) - Grandparents
- **Priority 3**: Gen 4+ (11 profiles) - Earlier ancestors
- Validate higher priority first to achieve 80% threshold faster

## Files

- `ancestry_validation_plan.json` - Contains all 29 profiles with FamilySearch search URLs
- `expanded_tree.json` - WikiTree data for all 32 profiles
- `familysearch_extracted_data.json` - Validated data (will be updated)
- `cross_source_analysis.json` - GPS compliance report (will be updated)

## Next Actions

1. **Start Automated Validation**:
   ```bash
   uv run python familysearch_batch_validator.py
   ```

2. **Or Manual Validation**:
   - Open `ancestry_validation_plan.json`
   - Visit each `familysearch_search_url`
   - Extract christening record data
   - Save to `familysearch_extracted_data.json`

3. **Generate GPS Compliance Report**:
   ```bash
   uv run python verify_tree.py cross-source
   ```

## Expected Challenges

### Geographic Constraints
- **Kent records**: Well-documented, likely good coverage
- **Norfolk records**: Good coverage for major parishes
- **Buckinghamshire/Oxfordshire**: May have gaps
- **Sussex (1647)**: Limited parish records survival

### Record Availability
- **Pre-1700**: Fewer surviving parish registers
- **1700-1800**: Good coverage in most areas
- **Post-1800**: Excellent coverage

### Naming Variations
- "Jeffery" vs "Jeffrey" vs "Jefferies" vs "Jeffcoat"
- Maiden names vs married names
- Name spelling variations in different records

## Success Metrics

- **Target**: 24+ of 29 profiles validated (83%)
- **Good**: 20-23 profiles validated (69-79%)
- **Acceptable**: 16-19 profiles validated (55-66%)

---

**Status**: Ready to begin validation
**Recommended Approach**: Automated Playwright extraction in batches
**Estimated Completion**: 2-3 hours
