# Wikidata Verification Checklist

**Date:** 2026-01-23
**Items to Verify:** 4

---

## Q137835093 - Archer L. Durham

### Required Claims (with sources)

| Property | Value | Source | Status |
|----------|-------|--------|--------|
| P31 (instance of) | Q5 (human) | - | ✅ Exists |
| P21 (sex/gender) | Q6581097 (male) | USAF Bio | ⬜ Verify source |
| P27 (citizenship) | Q30 (United States) | USAF Bio | ⬜ Verify source |
| P569 (date of birth) | 1932-06-09 | USAF Bio | ⬜ Verify source |
| P19 (place of birth) | Q49171 (Pasadena) | 1940 Census | ⬜ Verify source |
| P106 (occupation) | Q47064 (military officer) | USAF Bio | ⬜ Verify source |
| P241 (military branch) | Q11223 (USAF) | USAF Bio | ⬜ Verify source |
| P410 (military rank) | Q132851 (major general) | USAF Bio | ⬜ Verify source |
| P172 (ethnic group) | Q49085 (African Americans) | 1940 Census | ⬜ Verify source |

### New Claims to Add (from Featured Article)

| Property | Value | Source | Status |
|----------|-------|--------|--------|
| P69 (educated at) | Q192408 (Utah State) | USAF Bio | ⬜ Add |
| P69 (educated at) | Q327576 (GWU) | USAF Bio | ⬜ Add |
| P69 (educated at) | Q1967622 (National War College) | USAF Bio | ⬜ Add |
| P69 (educated at) | Q3603748 (Air Command Staff) | USAF Bio | ⬜ Add |
| P69 (educated at) | Q7581043 (Squadron Officer School) | USAF Bio | ⬜ Add |
| P69 (educated at) | Q5030053 (ICAF) | USAF Bio | ⬜ Add |
| P166 (award) | Q4698694 (AF DSM) | USAF Bio | ⬜ Add |
| P166 (award) | Q1181573 (DSSM) | USAF Bio | ⬜ Add |
| P166 (award) | Q719421 (Legion of Merit) x3 | USAF Bio | ⬜ Add |
| P166 (award) | Q1751805 (MSM) | USAF Bio | ⬜ Add |
| P166 (award) | Q4698684 (AFCM) | USAF Bio | ⬜ Add |
| P2031 (work period start) | 1953-01 | USAF Bio | ⬜ Add |
| P2032 (work period end) | 1989 | USAF Bio | ⬜ Add |
| P39 (position held) | Commander, 436th MAW | USAF Bio | ⬜ Add |
| P39 (position held) | Director of Deployment | USAF Bio | ⬜ Add |

### Constraint Checks

- [ ] P569 (birth date) < P570 (death date) - N/A (living)
- [ ] P19 (place of birth) should be location type
- [ ] P27 (citizenship) should match P19 country
- [ ] P410 (rank) should have P241 (branch) qualifier or separate claim
- [ ] All claims have references (P854 or P248)

---

## Q137856527 - Kate Manley

### Required Claims (with sources)

| Property | Value | Source | Status |
|----------|-------|--------|--------|
| P31 (instance of) | Q5 (human) | - | ⬜ Verify |
| P21 (sex/gender) | Q6581072 (female) | Dawes Rolls | ⬜ Verify source |
| P172 (ethnic group) | Q49085 (African Americans) | Dawes Rolls | ⬜ Verify source |
| P40 (child) | Q137856530 (Ida Manley) | Dawes Rolls | ⬜ Verify |

### Missing Claims

| Property | Value | Source | Status |
|----------|-------|--------|--------|
| P19 (place of birth) | Q841383 (Indian Territory) | Dawes Rolls | ⬜ Add |
| P551 (residence) | Vinita area | Dawes Rolls | ⬜ Add |

### Source References Required

- P854: https://www.okhistory.org/research/dawes
- P1810: "Kate Manley, Dawes Roll #4135, Card #1515"

---

## Q137856530 - Ida Manley

### Required Claims (with sources)

| Property | Value | Source | Status |
|----------|-------|--------|--------|
| P31 (instance of) | Q5 (human) | - | ⬜ Verify |
| P21 (sex/gender) | Q6581072 (female) | Dawes Rolls | ⬜ Verify source |
| P19 (place of birth) | Q841383 (Indian Territory) | Dawes Rolls | ⬜ Verify |
| P172 (ethnic group) | Q49085 (African Americans) | Dawes Rolls | ⬜ Verify source |
| P25 (mother) | Q137856527 (Kate Manley) | Dawes Rolls | ⬜ Verify |
| P26 (spouse) | Q137856532 (Morris Sorrell) | Dawes Rolls | ⬜ Verify |

### Missing Claims

| Property | Value | Source | Status |
|----------|-------|--------|--------|
| P2842 (marriage date) | 1902-10-05 | Dawes Rolls | ⬜ Add as qualifier to P26 |

### Source References Required

- P854: https://www.okhistory.org/research/dawes
- P1810: "Ida Manley, Dawes Roll #4136, Card #1515"

---

## Q137856532 - Morris A. Sorrell

### Required Claims (with sources)

| Property | Value | Source | Status |
|----------|-------|--------|--------|
| P31 (instance of) | Q5 (human) | - | ⬜ Verify |
| P21 (sex/gender) | Q6581097 (male) | Dawes Rolls | ⬜ Verify source |
| P569 (date of birth) | 1874-05-28 | Dawes Rolls | ⬜ Verify source |
| P19 (place of birth) | Q841383 (Indian Territory) | Dawes Rolls | ⬜ Verify |
| P172 (ethnic group) | Q49085 (African Americans) | Dawes Rolls | ⬜ Verify source |
| P26 (spouse) | Q137856530 (Ida Manley) | Dawes Rolls | ⬜ Verify |

### Missing Claims

| Property | Value | Source | Status |
|----------|-------|--------|--------|
| P2842 (marriage date) | 1902-10-05 | Dawes Rolls | ⬜ Add as qualifier to P26 |

### Source References Required

- P854: https://www.okhistory.org/research/dawes
- P1810: "Morris A. Sorrell, Cherokee Freedmen Card 193"

---

## Common Constraint Issues to Check

### For All Human Items (Q5)

1. **Birth before death**: P569 < P570 (if death date exists)
2. **Mother is female**: P25 target should have P21=Q6581072
3. **Father is male**: P22 target should have P21=Q6581097
4. **Spouse reciprocal**: If A P26 B, then B should P26 A
5. **Child reciprocal**: If A P40 B, then B should have P25 or P22 pointing to A
6. **Place of birth is location**: P19 target should be geographic entity
7. **References on all claims**: Every claim should have P854 or P248

### Wikidata Constraint Reports

Check these URLs for constraint violations:

- https://www.wikidata.org/wiki/Q137835093 (Durham)
- https://www.wikidata.org/wiki/Q137856527 (Kate Manley)
- https://www.wikidata.org/wiki/Q137856530 (Ida Manley)
- https://www.wikidata.org/wiki/Q137856532 (Morris Sorrell)

Look for the "Constraint violations" link in the sidebar on each item.

---

## Upload Instructions

### For archer_durham_additions.txt

1. Go to https://quickstatements.toolforge.org/
2. Login with Wikidata account
3. Click "New batch"
4. Paste contents (excluding comment lines starting with #)
5. Review the parsed statements
6. Execute batch

### Manual Verification Steps

1. After upload, visit each Wikidata item
2. Check "Constraint violations" in sidebar
3. Verify all sources display correctly
4. Check that qualifier dates are formatted properly
5. Ensure reciprocal relationships exist (spouse ↔ spouse, parent ↔ child)

---

## Source URLs

| Source | URL | Items Using |
|--------|-----|-------------|
| USAF Biography | https://www.af.mil/About-Us/Biographies/Display/Article/107179/major-general-archer-l-durham/ | Durham |
| Dawes Rolls Database | https://www.okhistory.org/research/dawes | Kate, Ida, Morris |
| Dover AFB Awards | https://www.dover.af.mil/News/Article/762117/team-dover-members-win-maj-gen-archer-l-durham-awards/ | Durham |
| 1940 Census | https://www.census.gov/ | Durham |

