# Validation Workflow - Complete Guide

**Current Status**: 3 of 32 validated (9%) - Need 21 more for GPS COMPLIANT

## 🎯 Quick Start (Fastest Path to GPS COMPLIANT)

### Step 1: Check Status
```bash
uv run python check_validation_status.py
```

### Step 2: Validate Tier 1 (6 profiles - 1.5 hours)
1. Open `manual_validation_batch_tier1.json`
2. For each of the 6 profiles:
   - Click the `search_url` to open FamilySearch
   - Find the christening record (usually first result)
   - Fill in the `familysearch_data` fields:
     - `person_name`: Full name from record
     - `birth_date`: Date from record (YYYY-MM-DD)
     - `birth_location`: Location from record
     - `familysearch_record_id`: Last part of URL (e.g., "JW2V-V1M")
     - `familysearch_url`: Full record URL
     - `relationships.father.name`: Father's name
     - `relationships.mother.name`: Mother's name
     - `notes`: Any discrepancies or observations
3. Save the file
4. Import: `uv run python import_manual_validations.py`

### Step 3: Check Progress
```bash
uv run python check_validation_status.py
```
Should show: 9 of 32 validated (28%)

### Step 4: Continue with Tier 2 (12 profiles - 2.5 hours)
```bash
# Same process with tier2 file
uv run python import_manual_validations.py manual_validation_batch_tier2.json
```
After: 21 of 32 validated (66%)

### Step 5: Complete Tier 3 for GPS COMPLIANT (6 profiles - 1.5 hours)
```bash
uv run python import_manual_validations.py manual_validation_batch_tier3.json
```
**Result**: 27 of 32 validated (84%) - **✅ GPS COMPLIANT!**

---

## 📁 Batch Files Available

| File | Profiles | Priority | Time | Cumulative % |
|------|----------|----------|------|--------------|
| `manual_validation_batch_tier1.json` | 6 | HIGH | 1.5h | 28% |
| `manual_validation_batch_tier2.json` | 12 | MEDIUM | 2.5h | 66% |
| `manual_validation_batch_tier3.json` | 6 | MEDIUM | 1.5h | **84%** ✅ |
| `manual_validation_batch_tier4.json` | 2 | LOW | 1h | 91% |

---

## 🔍 How to Find FamilySearch Records

### Example: Edward Jeffery (Jeffery-390)

1. **Open the search URL**:
   ```
   https://www.familysearch.org/search/record/results?givenName=Edward&surname=Jeffery&birthLikeYear=1765&birthLikePlace=Lamberhurst+Kent
   ```

2. **Look for matching record** (usually first result):
   - Name: Edward Jeffery
   - Event: Christening
   - Date: 29 Dec 1765 (or close)
   - Place: Lamberhurst, Kent

3. **Click the record** to open details page

4. **Extract information**:
   - Record URL: `https://www.familysearch.org/ark:/61903/1:1:XXXXX`
   - Record ID: `XXXXX` (last part of URL)
   - Father: Thomas Jeffery
   - Mother: Rachel Baldwin (or Rachel Jeffery)

5. **Fill in the JSON**:
```json
{
  "wikitree_id": "Jeffery-390",
  "familysearch_data": {
    "person_name": "Edward Jeffery",
    "birth_date": "1765-12-29",
    "birth_location": "Lamberhurst, Kent, England",
    "familysearch_record_id": "XXXXX",
    "familysearch_url": "https://www.familysearch.org/ark:/61903/1:1:XXXXX",
    "relationships": {
      "father": {"name": "Thomas Jeffery"},
      "mother": {"name": "Rachel Baldwin"}
    },
    "source": "FamilySearch",
    "source_collection": "England, Births and Christenings, 1538-1975",
    "extraction_confidence": "high",
    "extraction_method": "manual_entry",
    "notes": "Perfect match - all fields confirmed"
  }
}
```

---

## ⚠️ Common Situations

### No Exact Match Found
If you can't find an exact match:
- Try ±5 years on the date
- Try name variations (Jeffery vs Jeffrey)
- Try broader location (county instead of parish)
- If still no match, mark confidence as "low" or set status to "no_record_found"

### Mother's Maiden Name Unknown
Parish registers often only show mother's first name:
- Use father's name + location + date to confirm it's the right family
- Record what's shown: "Mary" or "Mary Jeffery" (married name)
- Add note: "Mother's maiden name not shown in register"

### Date Discrepancy
Birth vs christening dates can differ by weeks:
- Use the date shown in the record
- Add note: "Record shows christening date, birth was likely 1-6 weeks earlier"
- This is normal and acceptable

### Multiple People with Same Name
If you see multiple Edward Jefferys:
- Use father's name to distinguish
- Use exact location
- Use date range
- Choose the best match and note any uncertainty

---

## 🎓 Quality Guidelines

### High Confidence
- Name matches exactly
- Date within 1 month of WikiTree
- Location matches parish
- Both parents match

### Medium Confidence
- Name matches (minor spelling variation)
- Date within 6 months
- Location matches county
- At least one parent matches

### Low Confidence
- Name close but uncertain
- Date within 2 years
- Location matches region
- Parents partially match or unclear

### No Record Found
If you genuinely can't find a record:
```json
{
  "person_name": "",
  "birth_date": "",
  "birth_location": "",
  "familysearch_record_id": "",
  "familysearch_url": "",
  "relationships": {},
  "source": "FamilySearch",
  "source_collection": "England, Births and Christenings, 1538-1975",
  "extraction_confidence": "none",
  "extraction_method": "manual_entry",
  "notes": "No matching record found in FamilySearch. Tried variations of name, date ±5 years, and broader location search."
}
```

---

## 🚀 Workflow Scripts

### Check Current Status
```bash
uv run python check_validation_status.py
```
Shows: validated count, GPS status, next steps

### Generate All Batch Files
```bash
uv run python generate_all_batch_files.py
```
Creates/updates all tier batch files

### Import Completed Validations
```bash
# Import default (tier1)
uv run python import_manual_validations.py

# Import specific tier
uv run python import_manual_validations.py manual_validation_batch_tier2.json
```

### View Detailed Status
```bash
cat familysearch_extracted_data.json | python3 -m json.tool | less
```

---

## 📊 Progress Tracking

### Milestones

| Validated | % | Status | What This Means |
|-----------|---|--------|-----------------|
| 3 (now) | 9% | Starting | Original 3 profiles |
| 9 | 28% | Tier 1 done | All direct parents validated |
| 21 | 66% | Tier 2 done | Most grandparents validated |
| **24** | **75%** | **GPS THRESHOLD** | **Minimum for COMPLIANT** |
| 27 | 84% | Recommended | Strong confidence level |
| 32 | 100% | Complete | Perfect coverage |

### Time Estimates

- **To GPS COMPLIANT** (24 profiles): 5-6 hours total
  - Tier 1: 1.5 hours
  - Tier 2: 2.5 hours
  - Tier 3: 1.5 hours

- **To 100%** (32 profiles): 7-8 hours total
  - Add Tier 4: 1-2 hours (challenging records)

---

## 🎯 Success Tips

### Before You Start
1. Set aside uninterrupted time (1-2 hour blocks work best)
2. Have FamilySearch account ready (free account is fine)
3. Open `manual_validation_batch_tier1.json` in a good text editor
4. Keep this guide open for reference

### During Validation
1. Process one profile at a time - don't skip around
2. Save the batch file after every 2-3 profiles
3. Take breaks to maintain accuracy
4. When uncertain, add detailed notes
5. If a record is hard to find, spend max 5 minutes then move on

### After Each Session
1. Run import script immediately
2. Check status to see progress
3. Commit changes to git (if using version control)

### Keyboard Shortcuts (Text Editors)
- **VSCode**: Ctrl/Cmd + F to find empty fields
- **Most editors**: Search for `""` to find empty strings
- Use multi-cursor editing for repetitive fields

---

## ❓ Troubleshooting

### Import script says "not filled in"
- Check that ALL required fields have values (not empty strings "")
- Required: `person_name`, `birth_date`, `birth_location`
- Run the import with verbose mode to see which fields are missing

### Can't find a FamilySearch record
- Record may not exist or not be digitized
- Mark as "no_record_found" in notes
- Set extraction_confidence to "none"
- Move on - you can still reach GPS COMPLIANT without every record

### Made a mistake in imported data
- Edit `familysearch_extracted_data.json` directly
- Find the wikitree_id and correct the fields
- Re-run any downstream analysis

### Want to start over on a profile
- Delete the entry from `familysearch_extracted_data.json`
- Re-run the generation script: `uv run python generate_all_batch_files.py`
- Profile will appear in the batch file again

---

## 📈 What Happens After GPS COMPLIANT

Once you reach 24+ validated profiles (75%):

1. **Generate GPS Compliance Report**:
   ```bash
   uv run python verify_tree.py cross-source
   ```

2. **Review the report**:
   - Shows which relationships are confirmed
   - Identifies any conflicts
   - Calculates compliance percentage

3. **Optional: Continue to 100%**
   - Validate remaining profiles for complete coverage
   - Focus on Tier 4 (challenging records)

4. **Document Your Research**
   - Update WikiTree profiles with FamilySearch citations
   - Add source references to each profile
   - Document any unresolved discrepancies

---

**Last Updated**: 2026-01-26
**Current Progress**: 3/32 (9%)
**Next Action**: Open `manual_validation_batch_tier1.json` and start validating!
