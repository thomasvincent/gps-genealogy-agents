# Validation Tools - Ready to Use

**Status**: ✅ All validation tools created and tested
**Progress**: 3 of 32 profiles validated (9%)
**Goal**: Validate 24+ profiles for GPS COMPLIANT status

---

## 🎯 Quick Start (5 minutes to begin)

1. **Check current status**:
   ```bash
   uv run python check_validation_status.py
   ```

2. **Open first batch file**:
   ```bash
   open manual_validation_batch_tier1.json
   ```
   (Or use your preferred text editor)

3. **Start validating**:
   - For each profile, click the `search_url`
   - Find the christening record on FamilySearch
   - Fill in the `familysearch_data` fields
   - See `VALIDATION_WORKFLOW.md` for detailed instructions

4. **Import your work**:
   ```bash
   uv run python import_manual_validations.py
   ```

5. **Check progress**:
   ```bash
   uv run python check_validation_status.py
   ```

**That's it!** Repeat for remaining tiers to reach GPS COMPLIANT.

---

## 📁 Files Created (Validation Tools)

### Batch Files (Ready to Fill In)
- `manual_validation_batch_tier1.json` - **6 profiles (HIGH PRIORITY)**
- `manual_validation_batch_tier2.json` - 12 profiles
- `manual_validation_batch_tier3.json` - 6 profiles (reach GPS COMPLIANT)
- `manual_validation_batch_tier4.json` - 2 profiles (optional)

### Python Scripts
- `check_validation_status.py` - View current progress
- `import_manual_validations.py` - Import completed validations
- `generate_all_batch_files.py` - Regenerate batch files
- `auto_validate_batch.py` - Batch generation helper

### Documentation
- `VALIDATION_WORKFLOW.md` - **Complete step-by-step guide** ⭐
- `VALIDATION_COMPLETE_GUIDE.md` - Comprehensive strategy
- `MANUAL_VALIDATION_CHECKLIST.md` - Alternative workflow
- `README_VALIDATION.md` - This file

### Data Files
- `familysearch_extracted_data.json` - Validated records (3 so far)
- `ancestry_validation_results.json` - Validation structures

---

## 🎯 Validation Strategy

### Path to GPS COMPLIANT (24 profiles minimum)

```
Current: 3 profiles (9%)
    ↓ Tier 1 (1.5 hours)
    ↓ 6 profiles
    9 profiles (28%)
    ↓ Tier 2 (2.5 hours)
    ↓ 12 profiles
    21 profiles (66%)
    ↓ Tier 3 (1.5 hours)
    ↓ 6 profiles
    27 profiles (84%) ← ✅ GPS COMPLIANT!
    ↓ Tier 4 (optional)
    ↓ 2 profiles
    29 profiles (91%)
```

**Total Time**: ~5.5 hours to GPS COMPLIANT
**Total Time to 100%**: ~6.5 hours

---

## 📊 What You Get

### After Tier 1 (28% validated)
- All direct parents (Gen 2) verified
- Strong foundation for GPS compliance
- Clear relationships established

### After Tier 2 (66% validated)
- Most grandparents (Gen 3) verified
- Multiple lines of evidence
- Getting close to threshold

### After Tier 3 (84% validated) ✅
- **GPS COMPLIANT** status achieved
- High confidence in ancestry
- Publishable research quality

### After Tier 4 (91% validated)
- Exceptional coverage
- Even the challenging records validated
- Near-perfect documentation

---

## 🔧 Tool Reference

### Check Status Anytime
```bash
uv run python check_validation_status.py
```
**Output**:
- Progress bar
- Validated count
- GPS status
- List of validated profiles
- Next steps

**Use when**: You want to see where you are

---

### Import Completed Work
```bash
# Import tier 1 (default)
uv run python import_manual_validations.py

# Import specific tier
uv run python import_manual_validations.py manual_validation_batch_tier2.json
```
**What it does**:
- Reads the batch file
- Checks which profiles are filled in
- Adds them to familysearch_extracted_data.json
- Shows import summary and GPS status

**Use when**: You've filled in batch file entries

---

### Regenerate Batch Files
```bash
uv run python generate_all_batch_files.py
```
**What it does**:
- Creates all 4 tier batch files
- Skips already-validated profiles
- Updates profile counts

**Use when**: You want fresh batch files or made a mistake

---

## 📖 Detailed Guides

### For First-Time Validators
Read: `VALIDATION_WORKFLOW.md`
- Step-by-step instructions
- Examples with screenshots-style descriptions
- Common situations and how to handle them
- Quality guidelines
- Troubleshooting

### For Quick Reference
Read: `VALIDATION_COMPLETE_GUIDE.md`
- Validation strategy overview
- Priority tiers explained
- Search tips by region
- Expected challenges
- Success metrics

### For Alternative Workflow
Read: `MANUAL_VALIDATION_CHECKLIST.md`
- Checkbox-based approach
- All 29 profiles listed
- Validation criteria
- Space for notes

---

## 💡 Pro Tips

### Before You Start
1. ✅ Set aside 1-2 hour blocks of focused time
2. ✅ Have FamilySearch account ready (free account OK)
3. ✅ Use a good text editor (VSCode, Sublime, etc.)
4. ✅ Keep `VALIDATION_WORKFLOW.md` open for reference

### During Validation
1. 🎯 Process profiles in order - don't skip around
2. 💾 Save your work every 2-3 profiles
3. 🔍 Spend max 5 minutes per difficult record
4. 📝 Add detailed notes when uncertain
5. ☕ Take breaks to maintain accuracy

### After Each Session
1. ✅ Import immediately (`uv run python import_manual_validations.py`)
2. 📊 Check status (`uv run python check_validation_status.py`)
3. 💾 Commit to git (if using version control)
4. 🎉 Celebrate your progress!

---

## 🎓 What Makes a Good Validation

### Required Fields
- `person_name` - Full name from record
- `birth_date` - Date in YYYY-MM-DD format
- `birth_location` - Location from record

### Recommended Fields
- `familysearch_record_id` - For citation
- `familysearch_url` - For verification
- `relationships.father.name` - Parent confirmation
- `relationships.mother.name` - Parent confirmation

### Quality Indicators
- **High confidence**: All fields match, exact dates/locations
- **Medium confidence**: Minor variations, approximate dates
- **Low confidence**: Uncertain match, significant discrepancies

### Acceptable Variations
- ✅ Birth date vs christening date (typically 1-6 weeks apart)
- ✅ Spelling variations (Jeffery vs Jeffrey)
- ✅ Maiden name vs married name for mothers
- ✅ Abbreviated locations (Lamberhurst vs Lamberhurst, Kent)

---

## ❓ Common Questions

### Q: What if I can't find a FamilySearch record?
**A**: It's OK! Mark as "no_record_found" and move on. You can still reach GPS COMPLIANT without every single record.

### Q: Do I need a FamilySearch account?
**A**: Yes, but a free account works fine. Many records require login to view.

### Q: How long does each profile take?
**A**: Average 10-15 minutes. Easy ones: 5 min. Challenging: 20-30 min.

### Q: Can I work on multiple tiers at once?
**A**: Yes, but it's more efficient to complete one tier before starting the next.

### Q: What if I make a mistake?
**A**: Just edit `familysearch_extracted_data.json` directly and fix it. Or delete the entry and re-validate.

### Q: Can I pause and resume?
**A**: Absolutely! Save your batch file, import what you've done, and come back later. The system tracks what's completed.

### Q: What if dates don't match exactly?
**A**: That's normal. Use the date from the FamilySearch record and add a note explaining any discrepancy.

---

## 🎉 Success Metrics

### You'll Know You're Succeeding When:
- ✅ Import script shows increasing validated count
- ✅ Progress bar grows with each session
- ✅ GPS status changes from "Need X more" to lower numbers
- ✅ You're finding records quickly (getting faster with practice)
- ✅ Profile data matches WikiTree consistently

### GPS COMPLIANT Milestone:
When you reach **24 validated profiles (75%)**:
- 🎊 Congratulations! Your research meets GPS standards
- 📊 Generate compliance report: `uv run python verify_tree.py cross-source`
- 📝 Document your findings in WikiTree
- 🎯 Optional: Continue to 100% for exceptional coverage

---

## 📞 Next Steps

### Ready to Start? (5 minutes)

1. Run status check:
   ```bash
   uv run python check_validation_status.py
   ```

2. Open first batch file:
   ```bash
   open manual_validation_batch_tier1.json
   ```

3. Read the workflow guide:
   ```bash
   open VALIDATION_WORKFLOW.md
   ```

4. Begin validating!

### Need More Info First?

- **Detailed workflow**: `VALIDATION_WORKFLOW.md`
- **Strategy overview**: `VALIDATION_COMPLETE_GUIDE.md`
- **Alternative approach**: `MANUAL_VALIDATION_CHECKLIST.md`
- **Project summary**: `CURRENT_STATUS.md`

---

## 📈 Progress Tracking

### Current Status
```
███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 9%

3 of 32 validated
Need 21 more for GPS COMPLIANT
```

### Quick Commands
```bash
# Check status
uv run python check_validation_status.py

# Import work
uv run python import_manual_validations.py

# List batch files
ls -lh manual_validation_batch_*.json
```

---

**Ready to validate? Start with `manual_validation_batch_tier1.json`!**

---

**Last Updated**: 2026-01-26
**Tools Version**: 1.0
**Status**: ✅ Production Ready
