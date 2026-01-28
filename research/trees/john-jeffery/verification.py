"""
Unified family tree verification module.

Consolidates WikiTree live verification, FamilySearch extraction via Playwright,
and cross-source GPS Pillar 3 analysis.
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from gps_agents.sources.wikitree import WikiTreeSource


class TreeData:
    """Loads and manages tree data."""

    def __init__(self, tree_file: Path = Path("tree.json")):
        self.tree_file = tree_file
        self.data: dict[str, Any] = {}

    def load(self) -> None:
        """Load tree.json."""
        with open(self.tree_file) as f:
            self.data = json.load(f)

    def get_wikitree_ids(self) -> list[str]:
        """Extract WikiTree profile IDs."""
        ids = []
        for record in self.data.get("records", []):
            if record.get("source") == "WikiTree":
                wt_id = record.get("extracted_fields", {}).get("wikitree_id")
                if wt_id:
                    ids.append(wt_id)
        return ids

    def get_familysearch_records(self) -> list[dict]:
        """Get FamilySearch records."""
        return [
            r for r in self.data.get("records", [])
            if r.get("source") == "FamilySearch"
        ]

    def get_cached_wikitree_relationships(self) -> dict[str, dict]:
        """Extract family relationships from cached WikiTree records."""
        relationships = {}

        for record in self.data.get("records", []):
            if record.get("source") != "WikiTree":
                continue

            raw_data = record.get("raw_data", {})
            extracted = record.get("extracted_fields", {})

            person_name = f"{extracted.get('given_name', '')} {extracted.get('surname', '')}".strip()
            wikitree_id = extracted.get("wikitree_id")

            if not person_name or not wikitree_id:
                continue

            rels = {}

            # Father
            father_id = raw_data.get("Father")
            if father_id and raw_data.get("Parents", {}).get(str(father_id)):
                father_data = raw_data["Parents"][str(father_id)]
                father_name = f"{father_data.get('FirstName', '')} {father_data.get('LastNameAtBirth', '')}".strip()
                if father_name:
                    rels["father"] = {
                        "name": father_name,
                        "wikitree_id": father_data.get("Name"),
                        "birth_date": father_data.get("BirthDate"),
                        "death_date": father_data.get("DeathDate"),
                    }

            # Mother
            mother_id = raw_data.get("Mother")
            if mother_id and raw_data.get("Parents", {}).get(str(mother_id)):
                mother_data = raw_data["Parents"][str(mother_id)]
                mother_name = f"{mother_data.get('FirstName', '')} {mother_data.get('LastNameAtBirth', '')}".strip()
                if mother_name:
                    rels["mother"] = {
                        "name": mother_name,
                        "wikitree_id": mother_data.get("Name"),
                        "birth_date": mother_data.get("BirthDate"),
                        "death_date": mother_data.get("DeathDate"),
                    }

            relationships[wikitree_id] = {
                "person_name": person_name,
                "birth_date": extracted.get("birth_date"),
                "death_date": extracted.get("death_date"),
                "relationships": rels
            }

        return relationships


class WikiTreeVerifier:
    """Verifies WikiTree profiles against live API data."""

    def __init__(self):
        self.wikitree = WikiTreeSource()
        self.live_data: dict[str, dict] = {}

    async def fetch_profile(self, wikitree_id: str) -> Optional[dict]:
        """Fetch WikiTree profile data with full parent information."""
        params = {
            "action": "getPerson",
            "key": wikitree_id,
            "fields": "Id,Name,FirstName,LastNameAtBirth,LastNameCurrent,BirthDate,DeathDate,"
                      "BirthLocation,DeathLocation,Gender,Father,Mother,Touched,Parents",
            "getParents": "1",
            "format": "json",
        }

        try:
            data = await self.wikitree._make_wikitree_request(params)

            if isinstance(data, list) and data:
                first_item = data[0]
                if isinstance(first_item, dict):
                    return first_item.get("person")
            elif isinstance(data, dict):
                return data.get("getPerson", {}).get("person")

            return None

        except Exception as e:
            print(f"      Error fetching {wikitree_id}: {e}")
            return None

    async def verify_profiles(self, wikitree_ids: list[str]) -> dict[str, dict]:
        """Fetch and extract relationships from live WikiTree profiles."""
        live_relationships = {}

        for wt_id in wikitree_ids:
            profile_data = await self.fetch_profile(wt_id)
            if not profile_data:
                continue

            person_name = f"{profile_data.get('FirstName', '')} {profile_data.get('LastNameAtBirth', '')}".strip()

            relationships = {}

            # Father
            father_id = profile_data.get("Father")
            if father_id and profile_data.get("Parents", {}).get(str(father_id)):
                father_data = profile_data["Parents"][str(father_id)]
                father_name = f"{father_data.get('FirstName', '')} {father_data.get('LastNameAtBirth', '')}".strip()
                if father_name:
                    relationships["father"] = {
                        "name": father_name,
                        "wikitree_id": father_data.get("Name"),
                        "birth_date": father_data.get("BirthDate"),
                        "death_date": father_data.get("DeathDate"),
                    }

            # Mother
            mother_id = profile_data.get("Mother")
            if mother_id and profile_data.get("Parents", {}).get(str(mother_id)):
                mother_data = profile_data["Parents"][str(mother_id)]
                mother_name = f"{mother_data.get('FirstName', '')} {mother_data.get('LastNameAtBirth', '')}".strip()
                if mother_name:
                    relationships["mother"] = {
                        "name": mother_name,
                        "wikitree_id": mother_data.get("Name"),
                        "birth_date": mother_data.get("BirthDate"),
                        "death_date": mother_data.get("DeathDate"),
                    }

            live_relationships[wt_id] = {
                "person_name": person_name,
                "birth_date": profile_data.get("BirthDate"),
                "death_date": profile_data.get("DeathDate"),
                "birth_location": profile_data.get("BirthLocation"),
                "death_location": profile_data.get("DeathLocation"),
                "relationships": relationships,
                "touched": profile_data.get("Touched"),
            }

        self.live_data = live_relationships
        return live_relationships

    def compare_with_cached(self, cached: dict[str, dict]) -> dict:
        """Compare live data with cached records."""
        results = {
            "up_to_date": [],
            "modified": [],
            "missing_in_cache": [],
        }

        for wt_id, live_data in self.live_data.items():
            cached_data = cached.get(wt_id)

            if not cached_data:
                results["missing_in_cache"].append({
                    "wikitree_id": wt_id,
                    "person_name": live_data["person_name"],
                })
                continue

            # Check for changes
            changes = []
            rel_changes = []

            if cached_data.get("birth_date") != live_data.get("birth_date"):
                changes.append(f"Birth: {cached_data.get('birth_date')} → {live_data.get('birth_date')}")

            if cached_data.get("death_date") != live_data.get("death_date"):
                changes.append(f"Death: {cached_data.get('death_date')} → {live_data.get('death_date')}")

            cached_rels = cached_data.get("relationships", {})
            live_rels = live_data.get("relationships", {})

            for rel_type in ["father", "mother"]:
                cached_rel = cached_rels.get(rel_type)
                live_rel = live_rels.get(rel_type)

                if cached_rel and not live_rel:
                    rel_changes.append(f"{rel_type.title()} {cached_rel['name']} removed")
                elif live_rel and not cached_rel:
                    rel_changes.append(f"{rel_type.title()} {live_rel['name']} added")
                elif cached_rel and live_rel and cached_rel["name"] != live_rel["name"]:
                    rel_changes.append(f"{rel_type.title()}: {cached_rel['name']} → {live_rel['name']}")

            if changes or rel_changes:
                results["modified"].append({
                    "wikitree_id": wt_id,
                    "person_name": live_data["person_name"],
                    "person_changes": changes,
                    "relationship_changes": rel_changes,
                    "last_modified": live_data.get("touched"),
                })
            else:
                results["up_to_date"].append({
                    "wikitree_id": wt_id,
                    "person_name": live_data["person_name"],
                })

        return results


class FamilySearchVerifier:
    """Extracts FamilySearch family tree data via Playwright."""

    def __init__(self):
        self.extracted_data: dict[str, dict] = {}

    async def search_and_extract(self, person_name: str, birth_year: int, birth_place: str) -> Optional[dict]:
        """Search FamilySearch and extract family tree data using Playwright.

        This would use Playwright MCP tools to:
        1. Navigate to FamilySearch.org
        2. Search for the person
        3. Click on the person's profile
        4. Extract parent/spouse/child relationships
        5. Return structured data

        Note: Requires Playwright MCP tools integration.
        """
        # This is a placeholder - actual implementation requires MCP tool integration
        # In the CLI, we'll use browser_run_code to execute this
        return None

    def extract_relationships_from_page(self, person_name: str, page_html: str) -> dict:
        """Parse FamilySearch person page HTML to extract relationships."""
        # Parse HTML and extract family relationships
        # This is simplified - actual implementation needs proper HTML parsing
        return {
            "person_name": person_name,
            "father": None,
            "mother": None,
            "spouses": [],
            "children": [],
        }


class CrossSourceAnalyzer:
    """Analyzes GPS Pillar 3 compliance across sources."""

    def analyze(self, wikitree_data: dict[str, dict], familysearch_data: dict[str, dict]) -> dict:
        """Compare relationships across WikiTree and FamilySearch."""

        corroboration = {
            "confirmed": [],  # Both sources agree
            "conflicts": [],  # Sources disagree
            "wikitree_only": [],  # Only WikiTree has data
            "familysearch_only": [],  # Only FamilySearch has data
        }

        # Compare each person
        all_people = set(wikitree_data.keys()) | set(familysearch_data.keys())

        for person_key in all_people:
            wt_data = wikitree_data.get(person_key)
            fs_data = familysearch_data.get(person_key)

            if wt_data and not fs_data:
                corroboration["wikitree_only"].append({
                    "person": wt_data["person_name"],
                    "relationships": wt_data.get("relationships", {})
                })
            elif fs_data and not wt_data:
                corroboration["familysearch_only"].append({
                    "person": fs_data["person_name"],
                    "relationships": fs_data.get("relationships", {})
                })
            elif wt_data and fs_data:
                # Compare relationships
                wt_rels = wt_data.get("relationships", {})
                fs_rels = fs_data.get("relationships", {})

                for rel_type in ["father", "mother"]:
                    wt_rel = wt_rels.get(rel_type)
                    fs_rel = fs_rels.get(rel_type)

                    if wt_rel and fs_rel:
                        if wt_rel["name"] == fs_rel["name"]:
                            corroboration["confirmed"].append({
                                "person": wt_data["person_name"],
                                "relationship": rel_type,
                                "relative": wt_rel["name"],
                                "sources": ["WikiTree", "FamilySearch"]
                            })
                        else:
                            corroboration["conflicts"].append({
                                "person": wt_data["person_name"],
                                "relationship": rel_type,
                                "wikitree_says": wt_rel["name"],
                                "familysearch_says": fs_rel["name"]
                            })

        return corroboration

    def assess_gps_compliance(self, corroboration: dict) -> dict:
        """Assess GPS Pillar 3 compliance level."""

        total_relationships = (
            len(corroboration["confirmed"]) +
            len(corroboration["conflicts"]) +
            len(corroboration["wikitree_only"]) +
            len(corroboration["familysearch_only"])
        )

        if total_relationships == 0:
            status = "no_data"
            grade = "incomplete"
        elif corroboration["conflicts"]:
            status = "conflicts_exist"
            grade = "needs_resolution"
        elif corroboration["confirmed"]:
            confirmed_pct = len(corroboration["confirmed"]) / total_relationships * 100
            if confirmed_pct >= 80:
                status = "strong"
                grade = "compliant"
            elif confirmed_pct >= 50:
                status = "moderate"
                grade = "partial"
            else:
                status = "weak"
                grade = "incomplete"
        else:
            status = "single_source_only"
            grade = "incomplete"

        return {
            "status": status,
            "grade": grade,
            "total_relationships": total_relationships,
            "confirmed_count": len(corroboration["confirmed"]),
            "conflicts_count": len(corroboration["conflicts"]),
            "single_source_count": len(corroboration["wikitree_only"]) + len(corroboration["familysearch_only"]),
        }


def save_report(data: dict, filename: str) -> None:
    """Save report to JSON file."""
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)
