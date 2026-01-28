# Census Extraction Guide for John Jeffery

## What to Extract from Each Census

For GPS-compliant research, we need the following from each census enumeration:

### Critical Information (Must Have)
1. **Name** - Exact spelling as recorded
2. **Age** - To calculate birth year
3. **Relationship to Head** - (Head, Wife, Son, Daughter, Servant, etc.)
4. **Birthplace** - Parish/County/Country
5. **Address/Location** - Parish, Township, County
6. **Occupation** - Job/profession

### Additional Context (Should Have)
7. **Household Members** - All people enumerated in same household
8. **Enumeration Details** - Registration District, Sub-District, ED number
9. **Census Reference** - Piece, Folio, Page numbers (for citation)
10. **Neighbors** - Households before/after (helps confirm location)

---

## How to Access Your FamilySearch Records

### Step 1: Navigate to the Record
1. Go to https://www.familysearch.org
2. Sign in to your account
3. Go to your Person page or Search Records
4. Find the census sources you've attached

### Step 2: View the Original Image
Look for these buttons:
- **"View Image"** - Shows the original census page
- **"View Record"** - Shows the transcription
- **"Attach to Family Tree"** - Shows where it's linked

### Step 3: Record the Citation Information

For each census, copy this information:

```
CENSUS YEAR: [1841/1851/1861]

=== Citation Information ===
Collection: England and Wales Census, [YEAR]
Registration District:
Sub-District:
Enumeration District:
Piece:
Folio:
Page:
Line:
FamilySearch URL:

=== Person Information ===
Name (as recorded):
Age:
Sex:
Birthplace:
Occupation:
Relationship to Head:

=== Household Members ===
[List all people in household with their ages and relationships]

=== Address ===
Street/House:
Parish:
Township:
County:

=== Notes ===
[Any unusual spellings, annotations, or observations]
```

---

## Template for Each Census

### 1841 Census Template

```yaml
census_year: 1841
citation:
  collection: "England and Wales Census, 1841"
  registration_district: ""
  sub_district: ""
  enumeration_district: ""
  piece: ""
  folio: ""
  page: ""
  line: ""
  familysearch_url: ""

person:
  name: "John Jeffery"
  age: ""  # Ages rounded to nearest 5 in 1841
  sex: "M"
  occupation: ""
  birthplace: ""  # County only in 1841, Y=Yes (same county), N=No (different county)

household:
  - name: ""
    age: ""
    sex: ""
    occupation: ""
    birthplace: ""
    relationship: ""

address:
  street: ""
  parish: ""
  township: ""
  county: ""

notes: ""
```

### 1851 Census Template

```yaml
census_year: 1851
citation:
  collection: "England and Wales Census, 1851"
  registration_district: ""
  sub_district: ""
  enumeration_district: ""
  piece: ""
  folio: ""
  page: ""
  schedule: ""
  line: ""
  familysearch_url: ""

person:
  name: "John Jeffery"
  age: ""
  sex: "M"
  marital_status: ""  # Mar/Unm/Wid
  occupation: ""
  birthplace: ""  # Parish, County
  relationship_to_head: ""

household:
  - name: ""
    age: ""
    sex: ""
    marital_status: ""
    occupation: ""
    birthplace: ""
    relationship: ""

address:
  street: ""
  parish: ""
  township: ""
  county: ""

notes: ""
```

### 1861 Census Template

```yaml
census_year: 1861
citation:
  collection: "England and Wales Census, 1861"
  registration_district: ""
  sub_district: ""
  enumeration_district: ""
  piece: ""
  folio: ""
  page: ""
  schedule: ""
  line: ""
  familysearch_url: ""

person:
  name: "John Jeffery"
  age: ""
  sex: "M"
  marital_status: ""  # Mar/Unm/Wid
  occupation: ""
  birthplace: ""  # Parish, County
  relationship_to_head: ""
  employment_status: ""  # Employer/Employed/Neither

household:
  - name: ""
    age: ""
    sex: ""
    marital_status: ""
    occupation: ""
    birthplace: ""
    relationship: ""

address:
  street: ""
  parish: ""
  township: ""
  county: ""

notes: ""
```

---

## What This Data Will Tell Us

### Birth Year Calculation
Compare ages across censuses:
- 1841 (age X) → birth ~1841-X
- 1851 (age Y) → birth ~1851-Y
- 1861 (age Z) → birth ~1861-Z

**If consistent:** Strong evidence of same person
**If inconsistent:** Need to explain (age rounding, misreporting)

### Migration Tracking
- 1841 birthplace vs 1851 birthplace
- Change in county = evidence of migration
- "England" → "England" → "Not present" suggests emigration after 1861

### Family Identification
- Spouse name (if married)
- Children names and ages
- Parents (if living with them)

### Occupation Progression
- 1841: [occupation]
- 1851: [occupation]
- 1861: [occupation]
- Pattern shows economic status/stability

### Geographic Narrowing
- 1841-1861: Same parish = settled resident
- Moving parishes = transient/mobile
- Helps identify probable migration to US

---

## Once You Have the Data

Save each census transcription as a separate file:
- `research/trees/john-jeffery/census_1841.yaml`
- `research/trees/john-jeffery/census_1851.yaml`
- `research/trees/john-jeffery/census_1861.yaml`

Then run:
```bash
uv run python research/trees/john-jeffery/analyze_census.py
```

This will:
1. Extract birth year from ages
2. Identify spouse and children
3. Track geographic movement
4. Build household timeline
5. Flag inconsistencies
6. Generate GPS analysis

---

## Quick Tips

### Reading 1841 Census
- Ages rounded down to nearest 5 for adults (15→15, 23→20, 37→35)
- Birthplace: Y/N for "born in same county"
- No relationships listed (must infer)
- No specific birthplaces (county only)

### Reading 1851/1861 Census
- Exact ages (more reliable)
- Relationships clearly stated
- Specific birthplaces (parish + county)
- Marital status included

### Common Pitfalls
- Name variations (John/Jno/Jonathan)
- Age errors (±2 years common)
- Birthplace inconsistencies
- Occupation changes

---

## Example: What Good Data Looks Like

```yaml
census_year: 1851
citation:
  collection: "England and Wales Census, 1851"
  registration_district: "Tonbridge"
  sub_district: "Brenchley"
  enumeration_district: "1a"
  piece: "HO107/1618"
  folio: "234"
  page: "15"
  schedule: "78"
  familysearch_url: "https://www.familysearch.org/ark:/61903/1:1:XXXX-XXX"

person:
  name: "John Jeffery"
  age: "48"
  sex: "M"
  marital_status: "Mar"
  occupation: "Agricultural Labourer"
  birthplace: "Brenchley, Kent"
  relationship_to_head: "Head"

household:
  - name: "Mary Jeffery"
    age: "45"
    sex: "F"
    marital_status: "Mar"
    relationship: "Wife"
    birthplace: "Lamberhurst, Kent"
  - name: "Sarah Jeffery"
    age: "18"
    sex: "F"
    relationship: "Daughter"
    birthplace: "Brenchley, Kent"
  - name: "Thomas Jeffery"
    age: "12"
    sex: "M"
    relationship: "Son"
    birthplace: "Brenchley, Kent"

address:
  street: "High Street"
  parish: "Brenchley"
  township: "Brenchley"
  county: "Kent"
```

**This tells us:**
- Born ~1803 (1851-48=1803) ✓
- Married to Mary
- Living in Brenchley, Kent (his birthplace)
- Agricultural laborer
- Has daughter Sarah (born ~1833) who appears in death record
- Family stable in same location

---

## Need Help?

Once you extract the data, I can:
1. Analyze for GPS compliance
2. Calculate birth years and check consistency
3. Identify spouse/children for further research
4. Determine if this matches the Michigan emigrant
5. Generate Evidence Explained citations
