# John Jeffery Research Case - Census Extraction

## 📁 Your Files

```
research/trees/john-jeffery/
├── tree.json                      # Master research data (10 records)
├── tree.mmd                       # Visual diagram
├── research_notes.md              # GPS analysis & conflicts
├── 
├── census_1841.yaml              # ← FILL THIS IN (1841 census data)
├── census_1851.yaml              # ← FILL THIS IN (1851 census data)
├── census_1861.yaml              # ← FILL THIS IN (1861 census data)
├── 
├── EXAMPLE_census_1851.yaml      # Example showing what completed data looks like
├── census_extraction_guide.md    # Detailed extraction instructions
├── QUICKSTART.md                 # Quick start guide (READ THIS FIRST)
├── 
└── analyze_census.py             # Analysis script (run after filling in data)
```

## 🚀 Quick Start

### Step 1: Read the Quick Start Guide
```bash
open research/trees/john-jeffery/QUICKSTART.md
```

### Step 2: Fill in Census Templates
1. Go to FamilySearch.org
2. Find your John Jeffery census records (1841, 1851, 1861)
3. Open each YAML file and fill in the data:
   - `census_1841.yaml`
   - `census_1851.yaml`
   - `census_1861.yaml`

See `EXAMPLE_census_1851.yaml` for reference.

### Step 3: Run Analysis
```bash
cd research/trees/john-jeffery
uv run python analyze_census.py
```

## 📊 What the Analysis Will Tell You

✅ **Birth Year** - Calculated from ages across all censuses
✅ **Spouse Name** - Identified from household composition
✅ **Children** - Names and estimated birth years
✅ **Geographic Movement** - Did he stay in one place or move?
✅ **Consistency Check** - Are the records talking about the same person?
✅ **GPS Assessment** - How close are you to proof standard?

## 🎯 Key Questions to Answer

From the census records, we need:

1. **Spouse name** → Search for marriage record
2. **Children's names** → Track to Michigan
3. **Specific parish** → Search parish registers
4. **Consistency** → Prove same person across all 3 censuses

## 📖 What You Have So Far

### FamilySearch Records (Metadata Only)
- ✅ Marriage 1826 England
- ✅ Census 1841 England & Wales
- ✅ Census 1851 England & Wales
- ✅ Census 1861 England & Wales
- ✅ Death 1899 Michigan

### What's Missing
- ❌ Detailed census transcriptions (names, ages, locations)
- ❌ Marriage details (spouse maiden name, parish)
- ❌ Michigan death certificate details
- ❌ Evidence of migration (passenger lists)

## ⚠️ Critical Conflict

Your John Jeffery (died 1899 Michigan) conflicts with:
- WikiTree profile (died 1868 Kent, England)
- FindAGrave (died 1876)

**The census data will help prove these are different people.**

## 🔍 Next Steps After Census Extraction

Once you've filled in the census files:

1. **Run analysis** → Identify spouse and children
2. **Search Michigan** → Look for spouse/children in Michigan records
3. **Find migration** → Passenger lists England → USA (1861-1871)
4. **Get death certificate** → Michigan death certificate for John Jeffery
5. **GPS proof** → Write up evidence argument

## 📞 Getting Help

### If you can't find the FamilySearch records:
- Search: https://www.familysearch.org/search/catalog
- Use: "John Jeffery" + "1841" + "England census"

### If you can't read the images:
- Check FreeCEN transcriptions: http://www.freecen.org.uk
- Ask FamilySearch community for help

### If the script has errors:
- Check YAML syntax (compare to EXAMPLE file)
- Make sure indentation is correct (use spaces, not tabs)
- Verify all required fields are present

## 🎓 Learning Resources

- **Census Guide**: `census_extraction_guide.md` (detailed field-by-field instructions)
- **Quick Start**: `QUICKSTART.md` (step-by-step walkthrough)
- **Example**: `EXAMPLE_census_1851.yaml` (sample completed census)

---

**Ready to start?** Open `QUICKSTART.md` and follow along!
