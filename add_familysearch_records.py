"""Add FamilySearch records to John Jeffery research tree."""

import json
from datetime import datetime, UTC
from pathlib import Path

# Load existing tree
tree_path = Path("research/trees/john-jeffery/tree.json")
with open(tree_path) as f:
    tree = json.load(f)

# FamilySearch records provided by user
familysearch_records = [
    {
        "source": "FamilySearch",
        "record_id": "england-marriages-1538-1973",
        "record_type": "marriage",
        "url": None,  # User didn't provide specific URL
        "raw_data": {
            "title": "England Marriages, 1538–1973",
            "year": 1826,
            "location": "England",
            "created": "November 8, 2014",
            "creator": "FamilySearch"
        },
        "extracted_fields": {
            "full_name": "John Jeffery",
            "marriage_year": "1826",
            "marriage_place": "England"
        },
        "accessed_at": datetime.now(UTC).isoformat(),
        "confidence_hint": 0.8,  # Primary source
        "needs_translation": False,
        "language": "en"
    },
    {
        "source": "FamilySearch",
        "record_id": "england-wales-census-1841",
        "record_type": "census",
        "url": None,
        "raw_data": {
            "title": "England and Wales, Census, 1841",
            "year": 1841,
            "created": "September 22, 2023",
            "creator": "Sam McKnight"
        },
        "extracted_fields": {
            "full_name": "John Jeffery",
            "census_year": "1841",
            "census_place": "England and Wales"
        },
        "accessed_at": datetime.now(UTC).isoformat(),
        "confidence_hint": 0.9,  # Census is primary source
        "needs_translation": False,
        "language": "en"
    },
    {
        "source": "FamilySearch",
        "record_id": "england-wales-census-1851",
        "record_type": "census",
        "url": None,
        "raw_data": {
            "title": "England and Wales, Census, 1851",
            "year": 1851,
            "created": "September 2, 2018",
            "creator": "Cari_Walker",
            "note": "This source has not been attached to all people found in the record."
        },
        "extracted_fields": {
            "full_name": "John Jeffery",
            "census_year": "1851",
            "census_place": "England and Wales"
        },
        "accessed_at": datetime.now(UTC).isoformat(),
        "confidence_hint": 0.9,
        "needs_translation": False,
        "language": "en"
    },
    {
        "source": "FamilySearch",
        "record_id": "england-wales-census-1861",
        "record_type": "census",
        "url": None,
        "raw_data": {
            "title": "England and Wales, Census, 1861",
            "year": 1861,
            "created": "September 2, 2018",
            "creator": "Cari_Walker",
            "note": "This source has not been attached to all people found in the record."
        },
        "extracted_fields": {
            "full_name": "John Jeffery",
            "census_year": "1861",
            "census_place": "England and Wales"
        },
        "accessed_at": datetime.now(UTC).isoformat(),
        "confidence_hint": 0.9,
        "needs_translation": False,
        "language": "en"
    },
    {
        "source": "FamilySearch",
        "record_id": "michigan-deaths-burials-1800-1995",
        "record_type": "death",
        "url": None,
        "raw_data": {
            "title": "Michigan, Deaths and Burials, 1800-1995",
            "year": 1899,
            "location": "Michigan",
            "note": "John Jeffery in entry for Sarah Jeffery"
        },
        "extracted_fields": {
            "full_name": "John Jeffery",
            "death_year": "1899",
            "death_place": "Michigan"
        },
        "accessed_at": datetime.now(UTC).isoformat(),
        "confidence_hint": 0.9,  # Death records are primary sources
        "needs_translation": False,
        "language": "en"
    }
]

# Add records to tree
tree["records"].extend(familysearch_records)

# Update coverage
tree["coverage"]["records"] = len(tree["records"])
tree["coverage"]["primary"] += 5  # All FamilySearch records are primary sources
if "familysearch" not in tree["coverage"]["sources"]:
    tree["coverage"]["sources"].append("familysearch")

# Save updated tree
with open(tree_path, "w") as f:
    json.dump(tree, f, indent=2)

print(f"✓ Added {len(familysearch_records)} FamilySearch records")
print(f"✓ Total records in tree: {tree['coverage']['records']}")
print(f"✓ Primary sources: {tree['coverage']['primary']}")
print(f"✓ Updated: {tree_path}")
