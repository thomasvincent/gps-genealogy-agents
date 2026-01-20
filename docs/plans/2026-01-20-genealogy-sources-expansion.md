# Genealogy Sources Expansion

**Date:** 2026-01-20
**Status:** Approved

## Overview

Expand genealogy data sources to include cemetery records, military records, and community resources.

## Sources

### 1. AccessGenealogy (Extend)

**Current:** Native American records (Dawes Rolls, Cherokee, census)
**Adding:** Cemetery records by state, vital records

- Add state cemetery URLs (starting with California)
- Dynamic state list from cemetery index page
- New record type: `cemetery`

### 2. USGenWeb (New)

**URL:** `https://usgenweb.org`
**Auth:** Free
**Structure:** State/county hierarchy

Record types: census, cemetery, vital, military, land, court

Challenges:
- Volunteer-run, variable page structures
- Flexible parsing with fallbacks required

### 3. Fold3 (New)

**URL:** `https://www.fold3.com`
**Auth:** Free preview + optional subscription

Record types: military, pension, draft, naturalization

Implementation:
- Free search/preview without auth
- Full access with `FOLD3_API_KEY` or credentials
- Scrape results pages

### 4. RootsWeb (New)

**URL:** `https://www.rootsweb.com`
**Auth:** Free (Ancestry-funded)

Subdomains:
- `boards.rootsweb.com` - Message boards
- `lists.rootsweb.com` - Mailing list archives
- `sites.rootsweb.com/~obituary/` - Obituary Daily Times

Record types: message, obituary, mailing_list

## New Record Types

| Type | Description |
|------|-------------|
| `cemetery` | Burial/grave records |
| `military` | Service, pension, draft records |
| `vital` | Birth, marriage, death certificates |
| `obituary` | Death notices |
| `message` | Forum/mailing list posts |

## File Changes

| File | Action | Est. Lines |
|------|--------|------------|
| `accessgenealogy.py` | Extend | +50 |
| `usgenweb.py` | New | ~200 |
| `fold3.py` | New | ~250 |
| `rootsweb.py` | New | ~180 |
| `router.py` | Update | +10 |
| `models/search.py` | Add fields | +5 |

## SearchQuery Enhancement

```python
state: str | None = None
county: str | None = None
```

## Implementation Order

1. Extend AccessGenealogy with cemetery support
2. Create USGenWeb source
3. Create Fold3 source
4. Create RootsWeb source
5. Update router and models
6. Add tests
