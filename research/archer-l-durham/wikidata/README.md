# Wikidata Items for Durham-Sorrell-Manley Family

This directory contains prepared Wikidata items for genealogical subjects who meet [Wikidata:Notability](https://www.wikidata.org/wiki/Wikidata:Notability) criteria.

## Notability Assessment

| Person | Notable? | Justification |
|--------|----------|---------------|
| **Maj. Gen. Archer L. Durham** | ✅ YES | U.S. Air Force general officer with official biography |
| **Morris A. Sorrell** | ✅ YES | Dawes Roll Card 193 - permanent government identifier |
| **Ida Manley** | ✅ YES | Dawes Roll #4136 - permanent government identifier |
| **Kate Manley** | ✅ YES | Dawes Roll #4135 - permanent government identifier |
| Ruby Zenobia Sorrell | ❌ No | No permanent identifier in official records |
| Barney M. Durham | ❌ No | No permanent identifier beyond census |

## Files

### `archer_durham_quickstatements.txt`
[QuickStatements](https://quickstatements.toolforge.org/) V1 format for batch upload.

**How to use:**
1. Go to https://quickstatements.toolforge.org/
2. Login with your Wikidata account
3. Paste the contents (excluding comment lines)
4. Review and execute

### `archer_durham_wikidata.json`
JSON format documenting all claims, references, and relationships.

**Use for:**
- Manual item creation via Wikidata UI
- Documentation and review
- API-based uploads via wikibaseintegrator

## Upload Order

To enable relationship linking, create items in this order:

1. **Kate Manley** (great-grandmother) - Roll #4135
2. **Ida Manley** (grandmother) - Roll #4136, links to Kate as mother
3. **Morris A. Sorrell** (grandfather) - Card 193, links to Ida as spouse
4. **Archer L. Durham** (subject) - Links to family tree

## Wikidata Properties Used

| Property | Label | Used For |
|----------|-------|----------|
| P31 | instance of | Q5 (human) |
| P21 | sex or gender | Q6581097 (male), Q6581072 (female) |
| P27 | country of citizenship | Q30 (United States) |
| P569 | date of birth | ISO 8601 dates |
| P19 | place of birth | Location QIDs |
| P106 | occupation | Q47064 (military officer) |
| P241 | military branch | Q11223 (USAF) |
| P410 | military rank | Q132851 (major general) |
| P172 | ethnic group | Q49085 (African Americans) |
| P25 | mother | Person QID |
| P26 | spouse | Person QID |
| P40 | child | Person QID |

## References

All items include references to:
- [Oklahoma Historical Society Dawes Rolls Database](https://www.okhistory.org/research/dawes)
- [Official USAF Biography](https://www.af.mil/About-Us/Biographies/Display/Article/107179/major-general-archer-l-durham/) (for Archer Durham)
- 1940 United States Census

## Future Improvements

- [ ] Check if "Cherokee Freedmen" ethnic group exists in Wikidata (or create it)
- [ ] Propose Wikidata property for "Dawes Roll number" if not exists
- [ ] Add additional Manley siblings (Frank, Sarah, Lela, Joseph Jr., Willie, Daisy)
- [ ] Link to related items: Cherokee Freedmen, Dawes Commission, Treaty of 1866

## Source Documentation

All claims are supported by:
1. **Primary sources**: Dawes Rolls, USAF Biography, Census records
2. **Secondary sources**: Oklahoma Historical Society, FamilySearch collections
3. **GPS compliance**: Meets Genealogical Proof Standard with multiple independent sources
