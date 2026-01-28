# Census Extraction Quick Start Guide

## What You Need to Do

You have 3 FamilySearch census records to extract. Here's how:

### Step 1: Access Your FamilySearch Records

1. Go to https://www.familysearch.org and sign in
2. Navigate to the person or search results where you found these records
3. Click on each census source to view the full record

### Step 2: Fill Out the YAML Templates

Open these files and fill them in with data from FamilySearch:
- `census_1841.yaml` ← Fill this with 1841 census data
- `census_1851.yaml` ← Fill this with 1851 census data
- `census_1861.yaml` ← Fill this with 1861 census data

**See `EXAMPLE_census_1851.yaml` for what completed data looks like.**

### Step 3: What Information to Extract

For each census, you need:

#### Essential (Must Have)
- ✅ **Name** - Exactly as written
- ✅ **Age** - The number listed
- ✅ **Birthplace** - County/Parish where born
- ✅ **Occupation** - Job/profession
- ✅ **Address** - Parish, County at minimum
- ✅ **Household members** - Everyone in the same household

#### Important (Should Have)
- 📋 **FamilySearch URL** - Copy from browser address bar
- 📋 **Piece/Folio/Page** - Census reference numbers
- 📋 **Registration District** - Administrative area
- 📋 **Relationship** - How each person relates to head of household

### Step 4: Run the Analysis

Once you've filled in at least one census file:

```bash
cd research/trees/john-jeffery
uv run python analyze_census.py
```

This will:
- Calculate birth year from ages
- Identify spouse and children
- Track geographic movement
- Check for consistency
- Generate GPS assessment

---

## Key Questions to Answer from Census Data

### From 1841 Census:
- **Where was he living?** (Parish, County)
- **What was his occupation?**
- **Who was in the household?** (Wife? Children? Names?)
- **Birthplace?** (Y/N for same county, or Scotland/Ireland/Foreign)

### From 1851 Census:
- **Exact age?** (to calculate birth year: 1851 - age)
- **Married?** (Status column: Mar/Unm/Wid)
- **Wife's name?** (Look for "Wife" relationship)
- **Children?** (Names and ages)
- **Specific birthplace?** (Parish, County - e.g., "Brenchley, Kent")

### From 1861 Census:
- **Same household as 1851?** (Wife/children present?)
- **Same location?** (Still in same parish?)
- **Age consistent?** (Should be 10 years older than 1851)
- **Any older children left home?**
- **Any new children born 1851-1861?**

---

## What This Data Proves

### ✓ Identity Confirmation
If birth year is consistent across all 3 censuses (±2 years), this confirms same person.

**Example:**
- 1841: Age 38 → Born ~1803
- 1851: Age 48 → Born ~1803
- 1861: Age 58 → Born ~1803
**Result: ✓ CONSISTENT - Same person**

### ✓ Family Identification
Spouse name and children's names help:
- Search for marriage record (spouse's maiden name)
- Track children to Michigan (did they emigrate too?)
- Search for death records (spouse's death may mention John)

**Example:**
If 1851 shows wife "Mary Jeffery née Smith", search for:
- "John Jeffery" marriage to "Mary Smith" ~1825-1830
- Children Sarah, Thomas in Michigan records
- Mary's death record in Michigan (may give John's info)

### ✓ Geographic Timeline
Shows where to search next:
- All 3 censuses in Kent → Search Kent parish registers
- Not in 1871 England census → Emigrated 1861-1871
- Death 1899 Michigan → Search 1870-1890 Michigan records

### ✓ Migration Evidence
Missing from 1871 England census but appearing in Michigan death record proves emigration between 1861-1871.

**Search for:**
- Passenger lists Liverpool → New York (1861-1871)
- Michigan naturalization records
- Land patents in Michigan

---

## Common Issues & Solutions

### Issue: "I can't find the FamilySearch record"
**Solution:**
- Check your FamilySearch "Memories" or "Sources" tab
- Search FamilySearch catalog: https://www.familysearch.org/search/catalog
- Search for "John Jeffery" + "1841 census" + "England"

### Issue: "The census image is hard to read"
**Solution:**
- Use FamilySearch's transcription if available
- Check if FreeCEN has a transcription: http://www.freecen.org.uk
- Ask on FamilySearch community forums for help reading it

### Issue: "There are multiple John Jefferys on the page"
**Solution:**
- Use age to narrow down (born ~1803 = age ~38 in 1841)
- Look for spouse name if you know it
- Check birthplace column
- Compare occupations

### Issue: "Ages don't match between censuses"
**Solution:**
- ±2 years is normal (people misreported ages)
- 1841 ages were rounded (38 could be 38-42)
- Check if same household/location (confirms same person)

---

## After You Extract the Data

### Immediate Analysis
Run the Python script to get:
- Calculated birth year (with consistency check)
- Spouse identification
- List of children with birth years
- Geographic movement tracking

### Next Research Steps
The analysis will tell you:
1. **If data is consistent** → Can confidently say this is your ancestor
2. **Spouse name** → Search marriage records
3. **Children's names** → Search Michigan records for them
4. **Parish location** → Search parish registers for birth/marriage
5. **Occupation** → Helps understand economic status, migration motivation

### GPS Compliance
Once you have all 3 censuses extracted:
- ✅ Pillar 1: Exhaustive search (have primary England records)
- ✅ Pillar 2: Complete citations (will have full census references)
- ✅ Pillar 3: Analysis (script provides correlation analysis)
- ⚠️  Pillar 4: Still need Michigan records to resolve conflicts
- ⚠️  Pillar 5: Need to write proof argument

---

## Need Help?

1. **Can't access FamilySearch?** → Create free account at FamilySearch.org
2. **Record not attached?** → Search FamilySearch catalog manually
3. **Image unclear?** → Check FreeCEN.org transcriptions
4. **Script errors?** → Make sure YAML syntax is correct (use EXAMPLE as guide)
5. **Questions?** → Share your census data and I'll analyze it

---

## Example Workflow

1. Open `census_1851.yaml` in text editor
2. Go to FamilySearch, find 1851 census record
3. Fill in:
   - Name: "John Jeffery"
   - Age: "48"
   - Birthplace: "Brenchley, Kent"
   - Wife: "Mary Jeffery, age 45"
   - Children: "Sarah 18, Thomas 12, Elizabeth 8"
   - Parish: "Brenchley"
   - County: "Kent"
4. Save file
5. Run: `uv run python analyze_census.py`
6. Review output:
   - Birth year: ~1803 ✓
   - Spouse: Mary ✓
   - Children: Sarah (1833), Thomas (1839), Elizabeth (1843) ✓

7. Search for Sarah Jeffery in Michigan (she'd be ~66 in 1899 when father died)
8. If Sarah is in Michigan → Confirms family emigrated together
