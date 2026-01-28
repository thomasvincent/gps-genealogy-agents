# John Jeffery Research Case - Complete Documentation Index
## Navigation Guide for All Research Materials

**Last Updated**: 2026-01-27
**Research Status**: Disambiguation in progress (98.2% GPS compliant, conflicting death records)

---

## 🚀 Quick Start (NEW HERE?)

**If you're new to this research, start here:**

1. **[QUICKSTART.md](./QUICKSTART.md)** - Step-by-step walkthrough for beginners
2. **[RESEARCH-STATUS-REPORT.md](./RESEARCH-STATUS-REPORT.md)** - Complete analysis of current state
3. **[DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md)** - What to do next

---

## 📊 Current Research Status

| Metric | Value |
|--------|-------|
| **Profiles Validated** | 213 of 217 (98.2%) |
| **Relationships Confirmed** | 360 of 360 (100%) |
| **GPS Pillar 3 Status** | ✅ COMPLIANT |
| **Critical Issue** | ⚠️ Death record conflicts (Kent 1868 vs. Michigan 1899) |
| **Primary Sources** | 6 (1.7% - needs improvement) |
| **Secondary Sources** | 354 (98.3% - too high) |

**Action Required**: Disambiguate John Jeffery candidates using census records

---

## 📁 Documentation Organization

### 🎯 **Strategic Analysis** (Start Here If Resuming Research)

These documents analyze the overall research state and provide strategic direction:

| File | Purpose | Read If... |
|------|---------|------------|
| **[RESEARCH-STATUS-REPORT.md](./RESEARCH-STATUS-REPORT.md)** | Comprehensive analysis of conflicts, disambiguation strategy, GPS assessment | You need to understand what's been done and what needs fixing |
| **[DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md)** | Action-oriented checklist with costs, timelines, decision tree | You're ready to start resolving the conflicts |
| **[research_notes.md](./research_notes.md)** | Original GPS analysis and conflict identification | You want the earlier analysis notes |

### 📋 **Workflow Guides** (Step-by-Step Instructions)

These documents provide detailed instructions for specific tasks:

| File | Purpose | Read If... |
|------|---------|------------|
| **[QUICKSTART.md](./QUICKSTART.md)** | Beginner-friendly introduction to the research | You're brand new to this project |
| **[README.md](./README.md)** | Census extraction workflow (YAML templates) | You're ready to extract census data manually |
| **[census_extraction_guide.md](./census_extraction_guide.md)** | Field-by-field census extraction instructions | You need help reading census images |

### 📈 **Status Reports** (Progress Tracking)

These documents track research progress over time:

| File | Purpose | Last Updated |
|------|---------|--------------|
| **[CURRENT_STATUS.md](./CURRENT_STATUS.md)** | Overall status snapshot | 2026-01-26 |
| **[SUMMARY.md](./SUMMARY.md)** | Research summary | 2026-01-26 |
| **[EXPANSION_RESULTS.md](./EXPANSION_RESULTS.md)** | Tree expansion results | 2026-01-25 |
| **[CONTINUOUS_EXPANSION_STATUS.md](./CONTINUOUS_EXPANSION_STATUS.md)** | Automated expansion status | 2026-01-26 |
| **[PRIMARY_VALIDATION_STATUS.md](./PRIMARY_VALIDATION_STATUS.md)** | Primary source validation progress | 2026-01-26 |

### 🔍 **Validation Documentation** (Data Quality)

These documents explain the validation processes and results:

| File | Purpose | Read If... |
|------|---------|------------|
| **[README_VALIDATION.md](./README_VALIDATION.md)** | Validation workflow overview | You want to understand how data was verified |
| **[README_PRIMARY_SOURCE_VALIDATION.md](./README_PRIMARY_SOURCE_VALIDATION.md)** | Primary source validation details | You're working on increasing primary source ratio |
| **[README_AUTOMATED_EXPANSION.md](./README_AUTOMATED_EXPANSION.md)** | Automated expansion process | You want to know how the tree was grown to 217 profiles |
| **[VALIDATION_COMPLETE.md](./VALIDATION_COMPLETE.md)** | Validation completion report | You want final validation results |
| **[VALIDATION_COMPLETE_GUIDE.md](./VALIDATION_COMPLETE_GUIDE.md)** | Guide to validation completion | You're finishing up validation work |
| **[VALIDATION_STATUS.md](./VALIDATION_STATUS.md)** | Current validation status | You want current validation metrics |
| **[VALIDATION_WORKFLOW.md](./VALIDATION_WORKFLOW.md)** | Detailed validation workflow | You want step-by-step validation process |
| **[MANUAL_VALIDATION_CHECKLIST.md](./MANUAL_VALIDATION_CHECKLIST.md)** | Manual validation tasks | You're doing manual verification work |

### 🔧 **Technical Documentation** (For Developers)

These documents explain the technical aspects of the research system:

| File | Purpose | Read If... |
|------|---------|------------|
| **[FAMILYSEARCH_SETUP.md](./FAMILYSEARCH_SETUP.md)** | FamilySearch API setup instructions | You're setting up FamilySearch integration |
| **[INTEGRATION_SUMMARY.md](./INTEGRATION_SUMMARY.md)** | Summary of integrations | You want to understand the data sources |
| **[VERIFICATION_CLI.md](./VERIFICATION_CLI.md)** | Command-line verification tools | You're using verification scripts |
| **[VERIFICATION_SUMMARY.md](./VERIFICATION_SUMMARY.md)** | Verification results summary | You want verification metrics |
| **[RATE_LIMITING.md](./RATE_LIMITING.md)** | Rate limiting strategy | You're running automated scripts |
| **[RATE_LIMITING_AUDIT.md](./RATE_LIMITING_AUDIT.md)** | Rate limiting audit results | You need rate limit details |
| **[ANCESTRY_EXPANSION_PLAN.md](./ANCESTRY_EXPANSION_PLAN.md)** | Ancestry.com expansion plan | You're expanding via Ancestry |

---

## 🗂️ Data Files

### Tree Data (JSON)

| File | Contents | Size |
|------|----------|------|
| **tree.json** | Seed person + initial 10 records | ~35 KB |
| **tree_detailed.json** | Full tree structure | Large |
| **expanded_tree.json** | 217 validated profiles | Large |
| **gps_compliance_report.json** | GPS validation results | 33 KB+ |

### Census Data (YAML Templates)

| File | Purpose | Status |
|------|---------|--------|
| **census_1841.yaml** | 1841 England census data | ⚠️ Needs completion |
| **census_1851.yaml** | 1851 England census data | ⚠️ Needs completion |
| **census_1861.yaml** | 1861 England census data | ⚠️ Needs completion |
| **EXAMPLE_census_1851.yaml** | Example showing completed format | ✅ Reference only |

### Validation Data (JSON)

See the [🔍 Validation Documentation](#-validation-documentation-data-quality) section above for details on these files:
- `family_tree_verification.json`
- `live_tree_verification.json`
- `cross_source_verification.json`
- `wikitree_verification.json`
- `ancestry_validation_results.json`
- Plus ~20 more validation/progress tracking JSON files

---

## 🖼️ Visual Diagrams (Mermaid)

| File | Description | Best Viewed In |
|------|-------------|----------------|
| **tree.mmd** | Overview with conflict warnings | VS Code Mermaid extension / mermaid.live |
| **tree_detailed.mmd** | Full 217-profile tree | VS Code (may be large) |
| **ancestry_tree.mmd** | Ancestry-specific visualization | VS Code Mermaid extension |

**To view**: Open in VS Code with Mermaid extension, or copy-paste into https://mermaid.live/

---

## 🐍 Python Scripts

### Analysis Scripts

| Script | Purpose | Run With |
|--------|---------|----------|
| **analyze_census.py** | Analyze completed census YAML files | `uv run python analyze_census.py` |
| **generate_gps_report.py** | Generate GPS compliance report | `uv run python generate_gps_report.py` |
| **check_expansion_progress.py** | Check tree expansion status | `uv run python check_expansion_progress.py` |
| **check_validation_status.py** | Check validation status | `uv run python check_validation_status.py` |

### Expansion Scripts

| Script | Purpose | Run With |
|--------|---------|----------|
| **expand_tree.py** | Original tree expansion script | `uv run python expand_tree.py` |
| **expand_tree_v2.py** | Improved tree expansion | `uv run python expand_tree_v2.py` |
| **continuous_expansion.py** | Automated continuous expansion | `uv run python continuous_expansion.py` |

### Validation Scripts

| Script | Purpose | Run With |
|--------|---------|----------|
| **verify_tree.py** | Tree structure verification | `uv run python verify_tree.py` |
| **verification.py** | General verification tasks | `uv run python verification.py` |
| **validate_ancestry.py** | Ancestry.com validation | `uv run python validate_ancestry.py` |
| **auto_validate_batch.py** | Batch validation automation | `uv run python auto_validate_batch.py` |
| **familysearch_batch_validator.py** | FamilySearch batch validation | `uv run python familysearch_batch_validator.py` |
| **familysearch_primary_validator.py** | FamilySearch primary source validation | `uv run python familysearch_primary_validator.py` |
| **comprehensive_primary_validator.py** | Comprehensive primary validation | `uv run python comprehensive_primary_validator.py` |
| **stealthy_census_validator.py** | Census validation with rate limiting | `uv run python stealthy_census_validator.py` |

### Utility Scripts

| Script | Purpose | Run With |
|--------|---------|----------|
| **familysearch_login.py** | FamilySearch authentication | `uv run python familysearch_login.py` |
| **generate_all_batch_files.py** | Generate batch validation files | `uv run python generate_all_batch_files.py` |
| **import_manual_validations.py** | Import manual validation results | `uv run python import_manual_validations.py` |
| **add_familysearch_validation.py** | Add FamilySearch validation data | `uv run python add_familysearch_validation.py` |
| **auto_generate_wikitree_validations.py** | Generate WikiTree validations | `uv run python auto_generate_wikitree_validations.py` |

---

## 📖 Reading Order Recommendations

### For New Researchers

1. **[QUICKSTART.md](./QUICKSTART.md)** - Understand what this research is about
2. **[RESEARCH-STATUS-REPORT.md](./RESEARCH-STATUS-REPORT.md)** - See the big picture and current challenges
3. **[DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md)** - Understand what needs to be done next
4. **[README.md](./README.md)** - Learn how to extract census data (the next step)

### For Returning Researchers

1. **[CURRENT_STATUS.md](./CURRENT_STATUS.md)** - Quick status check
2. **[RESEARCH-STATUS-REPORT.md](./RESEARCH-STATUS-REPORT.md)** - Updated analysis
3. **[DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md)** - Pick up where you left off

### For Technical Users

1. **[README_VALIDATION.md](./README_VALIDATION.md)** - Understand validation system
2. **[README_AUTOMATED_EXPANSION.md](./README_AUTOMATED_EXPANSION.md)** - Understand tree expansion
3. **[FAMILYSEARCH_SETUP.md](./FAMILYSEARCH_SETUP.md)** - Set up integrations
4. **Run scripts** as needed from the [Python Scripts](#-python-scripts) section

### For GPS Reviewers

1. **[gps_compliance_report.json](./gps_compliance_report.json)** - Raw compliance data
2. **[RESEARCH-STATUS-REPORT.md](./RESEARCH-STATUS-REPORT.md)** - GPS Pillar analysis (Section VII)
3. **[VALIDATION_COMPLETE.md](./VALIDATION_COMPLETE.md)** - Validation completion status
4. **[PRIMARY_VALIDATION_STATUS.md](./PRIMARY_VALIDATION_STATUS.md)** - Primary source metrics

---

## 🎯 Current Priority Tasks

Based on the latest analysis ([RESEARCH-STATUS-REPORT.md](./RESEARCH-STATUS-REPORT.md)):

### Priority 1: Census Record Acquisition ⚠️ CRITICAL
- **What**: Access full 1841, 1851, 1861 England census images
- **Why**: Determine if John stayed in Kent or emigrated to Michigan
- **How**: Subscribe to FindMyPast (£12.95/month) or Ancestry (£14.99/month)
- **Timeline**: 1-2 hours
- **Next Step**: Fill in `census_1841.yaml`, `census_1851.yaml`, `census_1861.yaml`
- **Guide**: [census_extraction_guide.md](./census_extraction_guide.md)

### Priority 2: Death Certificate Acquisition
- **What**: Order death certificate (Kent 1868 OR Michigan 1899)
- **Why**: Confirm parents' names to definitively link to family tree
- **How**: UK GRO (£11) or Michigan state archives ($15)
- **Timeline**: 2-3 weeks (postal delivery)
- **When**: AFTER census records clarify which candidate to pursue

### Priority 3: Marriage Record Details
- **What**: Access 1826 England marriage record
- **Why**: Spouse's name can be cross-checked with census records
- **How**: FamilySearch (free) or parish register search
- **Timeline**: 1-2 days (if digitized), 2-4 weeks (if archive request)

See **[DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md)** for complete task list with decision tree.

---

## ⚠️ Known Issues & Warnings

### Critical Issues

1. **Conflated Death Records**
   - John Jeffery cannot have died in both 1868 Kent AND 1899 Michigan
   - Research cannot proceed until disambiguation is complete
   - **Do not publish** this tree until conflicts are resolved

2. **Low Primary Source Ratio**
   - Only 1.7% primary sources (6 of 360 records)
   - Heavy reliance on WikiTree user-contributed data
   - **Recommendation**: Replace with original certificates and documents

3. **Incomplete Census Data**
   - Census YAML files are partially filled but missing key details
   - **Action**: Complete census extraction using [README.md](./README.md) workflow

### Minor Issues

4. **Irrelevant Records**
   - FindAGrave #41806515 (William Dowling) is not relevant - marked for removal
   - WikiTree Jefferies-795 (Norfolk) is a different person - marked for removal
   - WikiTree Jeffcoat-237 (Buckinghamshire) is a different person - marked for removal

---

## 💡 Tips for Navigation

### Finding Information Quickly

- **Need a status update?** → [CURRENT_STATUS.md](./CURRENT_STATUS.md)
- **Need to know what to do next?** → [DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md)
- **Need to understand the big picture?** → [RESEARCH-STATUS-REPORT.md](./RESEARCH-STATUS-REPORT.md)
- **Need step-by-step instructions?** → [QUICKSTART.md](./QUICKSTART.md) or [README.md](./README.md)
- **Need technical details?** → Look in [Technical Documentation](#-technical-documentation-for-developers)
- **Need validation info?** → Look in [Validation Documentation](#-validation-documentation-data-quality)

### File Naming Conventions

- **ALL_CAPS.md** = Major documentation or status reports
- **lowercase.md** = Specific guides or notes
- **README_*.md** = Workflow guides for specific processes
- ***.json** = Data files (tree structure, validation results, progress tracking)
- ***.yaml** = Census data templates (for manual data entry)
- ***.py** = Python scripts for automation and analysis
- ***.mmd** = Mermaid diagram files (visual family trees)

---

## 📞 Getting Help

### If you're stuck:

1. **Read the guide first**: Most questions are answered in [QUICKSTART.md](./QUICKSTART.md) or [README.md](./README.md)
2. **Check the status**: See [CURRENT_STATUS.md](./CURRENT_STATUS.md) for recent progress
3. **Review the analysis**: [RESEARCH-STATUS-REPORT.md](./RESEARCH-STATUS-REPORT.md) explains all conflicts and issues
4. **Follow the checklist**: [DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md) provides step-by-step actions

### Common Questions

**Q: Which John Jeffery is this research about?**
A: That's the problem! See [RESEARCH-STATUS-REPORT.md](./RESEARCH-STATUS-REPORT.md) Section II for disambiguation analysis.

**Q: Why are there so many files?**
A: This is an automated research system that tracks progress in detail. Use [this INDEX.md file](#-documentation-organization) to navigate.

**Q: Can I publish this tree to WikiTree/Ancestry?**
A: **NO** - Not until disambiguation is complete. Publishing now would perpetuate incorrect data.

**Q: How much will it cost to fix this?**
A: £25-75 for disambiguation (see [DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md) "Budget Summary")

**Q: How long will it take?**
A: 2-4 weeks for disambiguation (see [DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md) "Timeline")

---

## 🚀 Next Steps (Action Plan)

1. **Read** [RESEARCH-STATUS-REPORT.md](./RESEARCH-STATUS-REPORT.md) (15-20 minutes)
2. **Review** [DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md) (10 minutes)
3. **Subscribe** to FindMyPast or Ancestry (5 minutes, £12.95)
4. **Extract** 1841 census data following [census_extraction_guide.md](./census_extraction_guide.md) (30-60 minutes)
5. **Fill in** `census_1841.yaml` (20 minutes)
6. **Repeat** for 1851 and 1861 censuses
7. **Run** `uv run python analyze_census.py` to check consistency
8. **Order** appropriate death certificate (Kent or Michigan)
9. **Wait** 2-3 weeks for certificate delivery
10. **Resolve** disambiguation using certificate + census data
11. **Re-validate** GPS compliance with `generate_gps_report.py`
12. **Publish** corrected research (WikiTree, Ancestry, FamilySearch)

**Estimated total time**: 4-5 weeks
**Estimated total cost**: £25-38

---

## 📝 Document History

| Date | Update | Files Changed |
|------|--------|---------------|
| 2026-01-25 | Initial research completed | tree.json, research_notes.md, tree.mmd |
| 2026-01-25 | Census extraction workflow created | README.md, census_*.yaml, QUICKSTART.md |
| 2026-01-26 | Automated expansion to 217 profiles | expanded_tree.json, tree_detailed.json |
| 2026-01-26 | GPS compliance validation run | gps_compliance_report.json |
| 2026-01-26 | Multiple validation scripts added | validate_*.py, familysearch_*.py |
| 2026-01-27 | Disambiguation analysis completed | RESEARCH-STATUS-REPORT.md, DISAMBIGUATION-CHECKLIST.md |
| 2026-01-27 | **INDEX.md created** | **INDEX.md (this file)** |

---

**Last Updated**: 2026-01-27
**Maintainer**: GPS Genealogy Project
**Research Subject**: John Jeffery (b. ~1803, England)
**Status**: Disambiguation in progress - **DO NOT PUBLISH UNTIL RESOLVED**

**For the most current action plan, always start with [DISAMBIGUATION-CHECKLIST.md](./DISAMBIGUATION-CHECKLIST.md).**
