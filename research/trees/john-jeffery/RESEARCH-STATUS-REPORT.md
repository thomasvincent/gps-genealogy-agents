# John Jeffery Research Case: Status Report
## GPS Genealogy Project - Disambiguation Analysis

**Generated**: 2026-01-27
**Research Subject**: John Jeffery (b. ~1803, England)
**GPS Compliance**: 98.2% (217 profiles validated)
**Critical Issue**: Multiple John Jeffery candidates with conflicting death records

---

## Executive Summary

The John Jeffery research case has achieved exceptional GPS Pillar 3 compliance (98.2% validation across 217 profiles, 360 confirmed relationships), representing months of systematic source validation. However, the research has surfaced a critical disambiguation challenge: **the automated search has collected records for at least 3-4 different individuals named John Jeffery born circa 1803 in England**.

**The core question**: Which John Jeffery is the research subject?

**Immediate Action Required**: Disambiguate the John Jeffery candidates using primary source analysis before expanding the tree further.

---

## I. Current Research State

### GPS Compliance Metrics

| Metric | Value | Status |
|--------|-------|--------|
| **Total Profiles** | 217 | ✅ Extensive |
| **Validated Profiles** | 213 | ✅ 98.2% |
| **Total Relationships** | 360 | ✅ Fully mapped |
| **Confirmed Relationships** | 360 | ✅ 100% |
| **Primary Sources** | 6 | ⚠️ Low ratio |
| **Secondary Sources** | 354 | ⚠️ High dependency |
| **GPS Pillar 3 Status** | **COMPLIANT** | ✅ Exceeds 75% standard |

**Assessment**: The tree meets GPS standards quantitatively but faces qualitative issues due to source conflation.

### Source Distribution

```
Primary Sources (6):
├─ FamilySearch Marriage 1826 (England)
├─ FamilySearch Census 1841 (England & Wales)
├─ FamilySearch Census 1851 (England & Wales)
├─ FamilySearch Census 1861 (England & Wales)
├─ FamilySearch Death 1899 (Michigan)
└─ [1 additional primary source]

Secondary Sources (354):
└─ Primarily WikiTree profiles (cascading family tree data)

Authored Sources (3):
├─ FindAGrave #240047451 (John Jeffery, 1803-1876)
├─ FindAGrave #41806515 (William Dowling - NOT RELEVANT)
└─ WikiTree profiles with user-contributed data
```

**Critical Observation**: The reliance on WikiTree as the primary source (354 secondary sources) means the tree's accuracy depends on WikiTree contributors' research quality. The conflicting death records suggest source data has been incorrectly merged.

---

## II. The Disambiguation Challenge

### Candidate A: John Jeffery (Kent, England)
**WikiTree ID**: Jeffery-538
**Birth**: 1803, Brenchley, Kent, England
**Death**: 1868, Tonbridge, Kent, England
**Parents**: Edward Jeffery (1765-1849) & Lydia Hickmott (1773-1808)
**Data Status**: "Certain" birth/death dates (WikiTree)
**Sources**: WikiTree profile with extensive family tree (217 profiles stem from this line)

**Profile Characteristics**:
- Remained in Kent throughout life
- Son of a Lamberhurst, Kent family
- Mother died when he was 5 years old (1808)
- Death 1868 at age 65 in Tonbridge, Kent

### Candidate B: John Jeffery (Michigan, USA)
**Source**: FamilySearch Death Record
**Birth**: ~1803, England (location unspecified)
**Death**: 1899, Michigan, USA
**Evidence**: Referenced in Sarah Jeffery's death record ("John Jeffery in entry for Sarah Jeffery")
**Sources**: FamilySearch collection "Michigan, Deaths and Burials, 1800-1995"

**Profile Characteristics**:
- Emigrated from England to Michigan (date unknown)
- Lived to age 96 (1803-1899)
- Mentioned as deceased in 1899 Michigan death record

### Candidate C: John Jeffery (Unknown Final Location)
**Source**: FindAGrave Memorial #240047451
**Birth**: 1803 (location not specified)
**Death**: 10 September 1876 (location not specified in excerpt)
**Evidence**: FindAGrave memorial

**Profile Characteristics**:
- Birth year matches seed (1803)
- Death date conflicts with both Candidate A (1868) and Candidate B (1899)

### Candidate D: John Jefferies (Norfolk, England)
**WikiTree ID**: Jefferies-795
**Birth**: 7 August 1803, Forncett St Mary, Norfolk, England
**Death**: Unknown
**Parents**: John Jefferies (1780-?) & Mary Hubbard (1781-?)
**Note**: Different spelling (Jefferies vs. Jeffery), different county (Norfolk vs. Kent)

**Assessment**: Likely a DIFFERENT PERSON due to different geographic origins and spelling variant.

### Candidate E: Joseph John Jeffcoat (Buckinghamshire → Illinois)
**WikiTree ID**: Jeffcoat-237
**Birth**: 19 October 1803, Aylesbury, Buckinghamshire, England
**Death**: 11 April 1870, Kankakee, Illinois, USA
**Parents**: John Jeffcoat (1776-1840) & Rebecca Fardon (1776-1838)
**Note**: Different surname (Jeffcoat), different first name (Joseph John), emigrated to Illinois

**Assessment**: DEFINITELY DIFFERENT PERSON - wrong surname and wrong given name.

---

## III. Conflict Analysis

### Death Date Conflicts

| Source | Death Date | Death Place | Age at Death | Reliability |
|--------|-----------|-------------|--------------|-------------|
| WikiTree Jeffery-538 | **1868** | Tonbridge, Kent | 65 | Medium (user-contributed) |
| FindAGrave 240047451 | **10 Sep 1876** | Unknown | 73 | Low (no location, memorial-only) |
| FamilySearch Michigan | **1899** | Michigan, USA | 96 | Medium (official death record) |

**The Problem**: These cannot all be the same person. A 31-year span exists between the earliest (1868) and latest (1899) death records.

### Geographic Conflicts

| Source | Geographic Pattern | Interpretation |
|--------|-------------------|----------------|
| WikiTree Jeffery-538 | Kent birth → Kent death | Stayed in England |
| FamilySearch Records | England birth → Michigan death | Emigrated to USA |

**The Problem**: Did John Jeffery remain in England (Kent) or emigrate to America (Michigan)?

### Census Trail Analysis

The FamilySearch census records (1841, 1851, 1861) show "John Jeffery" in England & Wales, but:
- **No specific location data** was extracted (just "England and Wales")
- **No household composition** was extracted
- **No occupation** was extracted
- **Confidence hints**: 0.9 (90%) but based on name match only

**Critical Flaw**: Without census enumeration district, household members, or occupations, we cannot distinguish between multiple John Jefferys living in England during the same period.

---

## IV. Root Cause: Data Conflation

### How the Conflict Arose

1. **Initial Seed**: John Jeffery, b. 1803, England (BROAD PARAMETERS)
2. **Automated Search**: Found multiple John Jefferys matching birth year and country
3. **WikiTree Integration**: Pulled WikiTree Jeffery-538 tree (Kent family, 217 profiles)
4. **FamilySearch Integration**: Added Michigan death record without checking geographic continuity
5. **Result**: Tree now contains data from 2-3 different John Jefferys merged as one person

### Why This Happens in Automated Research

**Name Commonality**: "John Jeffery" was a very common name in 19th-century England. Without distinctive middle names, specific parishes, or occupational data, disambiguation is challenging.

**Broad Geographic Scoping**: "England" as a birth place encompasses thousands of parishes across 40+ counties. Kent, Norfolk, and Buckinghamshire are hundreds of miles apart with distinct genealogical populations.

**WikiTree Cascading Effect**: Once WikiTree Jeffery-538's tree was integrated (217 profiles), the entire Kent family line became attached to the seed, making it difficult to assess whether the Michigan death record refers to the same individual or a different John Jeffery who emigrated.

---

## V. Disambiguation Strategy

### Step 1: Identify the Research Subject's Intent

**Question to clarify**: Is the research subject:
- **A**: The John Jeffery who remained in Kent (WikiTree Jeffery-538)?
- **B**: The John Jeffery who emigrated to Michigan and died 1899?
- **C**: An as-yet-unidentified John Jeffery matching neither profile?

**Method**: Examine the **original research intent** that created the seed:
- Was there a specific family story about emigration to America?
- Was there prior knowledge of a Kent-based family line?
- What prompted the choice of "John Jeffery, b. 1803, England" as the seed?

### Step 2: Acquire Detailed Census Records

**Current Problem**: The FamilySearch census entries (1841, 1851, 1861) lack crucial details.

**Action Required**: Manually access the **full census images** via FamilySearch, Ancestry, or FindMyPast to extract:
- **Enumeration District** (exact village/town)
- **Household Composition** (spouse name, children's names and ages)
- **Occupation** (provides class, skill level, and economic status)
- **Birthplace** (narrows geographic origin to specific parish)

**Why This Matters**: If the 1841/1851/1861 censuses show John Jeffery in **Brenchley or Tonbridge, Kent**, with a wife and children matching WikiTree Jeffery-538's family tree, then **Candidate A (Kent)** is confirmed and the Michigan record belongs to a different John Jeffery.

**Alternatively**: If the censuses show John Jeffery with **no family ties to Kent** or show him in a **port city like Liverpool or Southampton** (common emigration points), this suggests potential emigration, supporting **Candidate B (Michigan)**.

### Step 3: Search for Emigration Records (If Michigan is Correct)

**If pursuing Candidate B (Michigan John Jeffery)**:

**Required Sources**:
1. **Passenger Lists**: Search for "John Jeffery" departing England 1820s-1860s to USA
   - National Archives (Kew): BT 27 (outbound passenger lists)
   - Ancestry: UK and Ireland Outbound Passenger Lists
2. **US Naturalization Records**: Michigan naturalization records 1840s-1890s
   - NARA (National Archives): Naturalization records for Michigan
3. **Michigan Census Records**: 1850, 1860, 1870, 1880 US Federal Census in Michigan
   - Should show John Jeffery's household, occupation, and England birthplace
4. **Sarah Jeffery Death Record**: Full transcription needed (the 1899 Michigan record that mentions John Jeffery)
   - Determine if Sarah was John's wife, daughter, or other relation
   - Obtain death certificate details (parents' names, spouse name)

**Expected Outcome**: If John Jeffery emigrated to Michigan, there should be:
- A passenger list showing departure from England
- US census records 1850-1880 showing him in Michigan
- Possible naturalization records
- Family members (wife, children) also appearing in Michigan records

**If these records DON'T exist**: Candidate B is likely incorrect, and the Michigan death record refers to a different John Jeffery.

### Step 4: Verify FindAGrave Memorial 240047451

**Current Status**: FindAGrave memorial shows John Jeffery 1803-1876, but:
- **No cemetery name** extracted
- **No burial location** specified
- **No photograph** of headstone
- **No additional family members** linked

**Action Required**: Access the full FindAGrave memorial page:
- Identify the cemetery and location
- Check for family plot (spouse, children nearby?)
- Compare burial location to WikiTree Jeffery-538 death place (Tonbridge, Kent)
- Look for memorial creator's sources

**Possible Outcomes**:
- **If cemetery is in Kent**: Likely matches WikiTree Jeffery-538, but death date (1876) conflicts with WikiTree (1868) → needs correction
- **If cemetery is in Michigan**: Conflicts with 1899 death date → possible different John Jeffery
- **If cemetery is elsewhere**: Indicates a third John Jeffery

### Step 5: Reconcile or Split the Tree

**Option A: Reconcile (If All Records Match One Person)**
- Correct death date discrepancies (determine if 1868, 1876, or 1899 is accurate)
- Remove incorrect WikiTree profiles (Jefferies-795, Jeffcoat-237)
- Verify all 217 profiles belong to the confirmed John Jeffery's family tree

**Option B: Split (If Records Match Different People)**
1. Create **Candidate A Tree**: John Jeffery (Kent) with WikiTree Jeffery-538 family
   - Retain the 217 profiles connected to the Kent family
   - Mark as "remained in England"
2. Create **Candidate B Tree**: John Jeffery (Michigan) with FamilySearch records
   - Start new tree with Michigan death record as anchor point
   - Search for Michigan census and emigration records
   - Build out American branch of family
3. Classify **Candidates D & E** as "incorrect matches" and remove from active research

**Option C: Restart with Narrower Seed (If Original Subject is Unknown)**
- If neither Candidate A nor B matches the intended research subject, restart with:
  - **More specific birth location** (e.g., "Brenchley, Kent" vs. just "England")
  - **Additional identifying info** (occupation, spouse name, known children)
  - **Family story details** (emigration, military service, cause of death)

---

## VI. Primary Source Acquisition Plan

To resolve the disambiguation issue, the following primary sources must be obtained:

### Priority 1: Census Records (1841, 1851, 1861)
| Census | Access Method | Cost | Timeline |
|--------|--------------|------|----------|
| 1841 England & Wales | FindMyPast or Ancestry | £12.95/month subscription | Immediate |
| 1851 England & Wales | FindMyPast or Ancestry | £12.95/month subscription | Immediate |
| 1861 England & Wales | FindMyPast or Ancestry | £12.95/month subscription | Immediate |

**Objective**: Extract household composition, exact location, and occupation to confirm geographic pattern (Kent vs. emigration).

### Priority 2: Marriage Record (1826 England)
| Source | Access Method | Cost | Timeline |
|--------|--------------|------|----------|
| FamilySearch "England Marriages 1538-1973" | FamilySearch (free) | Free | Immediate |
| Parish registers (if FamilySearch image unavailable) | Kent Archives / county record office | £10-20 per search | 2-4 weeks |

**Objective**: Obtain marriage location, spouse's full name, fathers' names, and occupations to confirm identity and link to family tree.

### Priority 3: Death Records (1868/1876/1899)
| Source | Access Method | Cost | Timeline |
|--------|--------------|------|----------|
| 1868 Tonbridge, Kent death | FreeBMD → GRO certificate order | £11 (UK GRO) | 2-3 weeks |
| 1876 death (FindAGrave location TBD) | Depends on location | Varies | Depends |
| 1899 Michigan death | Michigan death certificates (Ancestry or state archives) | Ancestry subscription or $15 state fee | 1-2 weeks |

**Objective**: Confirm which death record is correct, obtain parents' names, spouse name, and cause of death for verification.

### Priority 4: Emigration Records (If Michigan Candidate)
| Source | Access Method | Cost | Timeline |
|--------|--------------|------|----------|
| UK Outbound Passenger Lists | Ancestry "UK and Ireland Outbound Passenger Lists" | Included in subscription | Immediate |
| US Naturalization (Michigan) | NARA or Ancestry | Free (NARA) or subscription (Ancestry) | 1-2 weeks |
| Michigan Census 1850-1880 | FamilySearch or Ancestry | Free (FS) or subscription (Ancestry) | Immediate |

**Objective**: Prove or disprove emigration to Michigan.

---

## VII. GPS Compliance Considerations

### Current Status: Compliant But Compromised

**GPS Pillar 3 (Thorough Research)**: ✅ Technically compliant at 98.2%
**GPS Pillar 1 (Reasonably Exhaustive Source Search)**: ⚠️ Compromised due to conflated sources
**GPS Pillar 2 (Complete and Accurate Citation)**: ⚠️ Uncertain which sources apply to which John Jeffery
**GPS Pillar 4 (Skillful Correlation and Analysis)**: ❌ **FAILING** due to unresolved conflicts
**GPS Pillar 5 (Sound Written Conclusion)**: ❌ **FAILING** - cannot write conclusion with conflicting death records

**Overall GPS Assessment**: The research **meets the numerical threshold** for Pillar 3 compliance but **fails the qualitative standard** because it conflates multiple individuals' records as one person.

### What GPS Standards Require

From the Genealogical Proof Standard:

> **Pillar 4**: "The analysis must be skillfully correlated and interpreted, considering all relevant evidence—including evidence that might contradict the proposed answer."

**Current Failure**: The conflicting death records (1868 Kent vs. 1899 Michigan) represent "evidence that might contradict the proposed answer," yet they have been incorporated into the tree without resolution.

> **Pillar 5**: "The conclusion must be coherently written and include documentation."

**Current Failure**: A "coherent conclusion" cannot be written when the subject's death date varies by 31 years and death location spans two continents.

### Path to True GPS Compliance

1. **Acknowledge the Conflict**: Document the disambiguation challenge in a research log
2. **Resolve Through Primary Sources**: Acquire and analyze census, marriage, and death records
3. **Choose or Split**: Either confirm one candidate and remove conflicting data, OR split into separate research cases
4. **Document the Resolution**: Write a clear conclusion explaining which records belong to the subject and why others were excluded
5. **Re-run GPS Validation**: After disambiguation, re-calculate GPS metrics to ensure compliance

**Timeline to Resolution**: 2-4 weeks (depending on document acquisition)
**Estimated Cost**: £25-75 (UK certificates + Ancestry subscription)

---

## VIII. Recommendations

### Immediate Actions (This Week)

1. **Clarify Research Intent** ✅ PRIORITY
   - Review the original seed creation: Why "John Jeffery, b. 1803, England"?
   - Was there family knowledge of emigration to Michigan?
   - Was there a connection to Kent mentioned in family stories?
   - **Purpose**: Determine which candidate (Kent vs. Michigan) to pursue

2. **Access Full Census Images** ✅ PRIORITY
   - Subscribe to FindMyPast or Ancestry (£12.95/month)
   - Search 1841 England census for "John Jeffery" born ~1803
   - Extract: exact location, household members, occupation
   - Repeat for 1851 and 1861 censuses
   - **Purpose**: Establish geographic continuity (stayed in Kent vs. possible emigration)

3. **Access FindAGrave Full Memorial**
   - Visit https://www.findagrave.com/memorial/240047451/john-jeffery
   - Identify cemetery name and location
   - Check for spouse/children memorials nearby
   - Review contributor's source notes
   - **Purpose**: Determine if 1876 death record matches Kent or Michigan candidate

### Short-Term Actions (2-4 Weeks)

4. **Order Death Certificates**
   - If Kent candidate: Order 1868 Tonbridge death certificate from UK GRO (£11)
   - If Michigan candidate: Order 1899 Michigan death certificate (Ancestry or state archives)
   - **Purpose**: Confirm parents' names to link definitively to family tree

5. **Search for Marriage Details**
   - Access FamilySearch "England Marriages 1538-1973" collection
   - Search for John Jeffery marriage ~1826
   - Extract: parish, spouse's full maiden name, fathers' names and occupations
   - **Purpose**: Spouse's name can be cross-checked with census records

6. **Michigan Census Search** (If pursuing Michigan candidate)
   - Search US Census 1850, 1860, 1870, 1880 for "John Jeffery" in Michigan
   - Look for England birthplace
   - Note household composition (matches English family?)
   - **Purpose**: Prove or disprove Michigan residence

### Medium-Term Actions (1-3 Months)

7. **Emigration Record Search** (If Michigan candidate is correct)
   - Search UK outbound passenger lists 1830s-1860s for John Jeffery to USA
   - Check port cities: Liverpool, Southampton, London
   - Search Michigan naturalization records 1840s-1890s
   - **Purpose**: Document emigration event

8. **Resolve or Split the Tree**
   - **If Kent is confirmed**: Remove Michigan death record, correct any WikiTree discrepancies (1868 vs. 1876)
   - **If Michigan is confirmed**: Remove WikiTree Jeffery-538 tree, start new Michigan-based tree
   - **If unresolvable**: Mark as "conflated" and restart with new seed

9. **Re-validate GPS Compliance**
   - After disambiguation, re-run GPS compliance report
   - Ensure all 217 profiles (if retaining Kent tree) or reduced set (if splitting) meet standards
   - Write formal research conclusion explaining resolution

### Long-Term Actions (Ongoing)

10. **Expand with Primary Sources**
    - Once identity is confirmed, prioritize primary sources over WikiTree data
    - Order birth certificates, marriage certificates, and wills for key ancestors
    - Replace WikiTree-sourced data with original documents where possible
    - **Goal**: Achieve 60%+ primary source ratio (currently 1.7%)

11. **Publish Findings**
    - Update WikiTree profile with corrected information and sources
    - Share disambiguation analysis with WikiTree community
    - Consider publishing in genealogy journal (e.g., *National Genealogical Society Quarterly*)

---

## IX. Cost-Benefit Analysis

### Option A: Continue with Current Tree (No Disambiguation)
**Cost**: £0
**Benefit**: None
**Risk**: **HIGH** - Publishing genealogically invalid research, violating GPS standards, perpetuating misinformation
**Recommendation**: ❌ **DO NOT PURSUE** - violates GPS Pillar 4 and 5

### Option B: Minimal Disambiguation (Census + One Death Certificate)
**Cost**: £25 (Ancestry 1-month + UK GRO certificate)
**Time**: 2-3 weeks
**Benefit**: Resolves Kent vs. Michigan question, meets GPS standards
**Risk**: Low - sufficient to determine correct candidate
**Recommendation**: ✅ **RECOMMENDED** - minimal investment, maximum clarity

### Option C: Comprehensive Primary Source Rebuild
**Cost**: £100-300 (certificates, subscriptions, archival searches)
**Time**: 3-6 months
**Benefit**: Gold-standard GPS compliance, publishable research
**Risk**: Very low - produces heirloom-quality family history
**Recommendation**: ✅ **RECOMMENDED FOR SERIOUS RESEARCHERS** - produces legacy-quality documentation

### Option D: Restart with New Seed
**Cost**: £0 (unless new searches required)
**Time**: 1-2 days (automated search), 1-3 months (manual validation)
**Benefit**: Clean slate, no conflated data
**Risk**: Medium - may discover the same disambiguation challenge with a different John Jeffery
**Recommendation**: ⚠️ **CONSIDER IF** original research intent is unclear or both candidates are wrong

---

## X. Technical Notes

### File Inventory

The john-jeffery directory contains 27 JSON files documenting extensive research:

```
Main Files:
├─ tree.json (seed and initial records)
├─ tree_detailed.json (full tree structure)
├─ gps_compliance_report.json (GPS validation results)
└─ expanded_tree.json (217 profiles)

Verification Files:
├─ family_tree_verification.json
├─ live_tree_verification.json
├─ cross_source_verification.json
├─ wikitree_verification.json
└─ ancestry_validation_results.json

Source-Specific Data:
├─ familysearch_census_results.json
├─ familysearch_extraction.json
├─ familysearch_search_urls.json
├─ familysearch_validation_progress.json
├─ familysearch_extracted_data.json
├─ census_fetch_cache.json
├─ census_validation_progress.json
└─ census_primary_data.json

Progress Tracking:
├─ expansion_progress.json
├─ continuous_expansion_progress.json
├─ validation_progress.json
├─ ancestry_validation_plan.json
├─ comprehensive_validation_progress.json
└─ comprehensive_primary_data.json

Manual Validation (Tiered):
├─ manual_validation_batch_tier1.json
├─ manual_validation_batch_tier2.json
├─ manual_validation_batch_tier3.json
└─ manual_validation_batch_tier4.json

Analysis:
└─ cross_source_analysis.json
```

**Total Data**: ~2-3 MB of structured genealogical data

### Mermaid Diagrams

Three Mermaid diagrams document the research:

```
├─ tree.mmd (overview with conflicts highlighted)
├─ tree_detailed.mmd (full 217-profile tree)
└─ ancestry_tree.mmd (ancestry-specific visualization)
```

**Current Status**: tree.mmd clearly identifies the disambiguation challenge with visual conflict warnings.

---

## XI. Conclusion

The John Jeffery research case represents **excellent quantitative research** (98.2% GPS compliance, 217 profiles, 360 confirmed relationships) undermined by a **critical qualitative flaw** (conflation of multiple individuals' records).

**The Path Forward**: Invest £25 and 2-3 weeks to acquire census and death records, disambiguate the candidates, and achieve true GPS compliance. This relatively small investment will transform the research from "technically compliant but qualitatively compromised" to "gold-standard genealogical proof."

**Why This Matters**: Genealogical research isn't just about collecting names and dates—it's about **accurate representation of individual lives**. Conflating John Jeffery of Kent (who died 1868 and never left England) with a different John Jeffery of Michigan (who emigrated and died 1899) is a disservice to both men and their descendants.

**Next Step**: Determine the research intent (Kent or Michigan) and acquire the 1841 census record to establish geographic baseline.

---

*Report compiled: 2026-01-27*
*Based on: gps_compliance_report.json (2026-01-26), tree.json, tree.mmd*
*Recommendation: Disambiguate within 2-4 weeks using Priority 1 and 2 sources*
*Estimated cost for resolution: £25-75*
*Expected outcome: GPS Pillar 4 & 5 compliance, publishable research*
