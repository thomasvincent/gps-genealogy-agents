"""Census-based family tree builder.

Builds family trees by working backwards through US Census records:
1. Start with seed person and known census records
2. Extract household members (parents, siblings) from census
3. Search for parents in older censuses (1940→1930→1920→1910...)
4. Iterate backwards through generations
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# US Census years available for searching
CENSUS_YEARS = [1950, 1940, 1930, 1920, 1910, 1900, 1890, 1880, 1870, 1860, 1850]


@dataclass
class CensusPerson:
    """A person extracted from census or research data."""

    given_name: str
    surname: str
    birth_year: int | None = None
    birth_place: str | None = None
    death_year: int | None = None
    death_place: str | None = None
    relation_to_head: str | None = None  # e.g., "head", "wife", "son", "daughter"
    census_year: int | None = None
    census_place: str | None = None
    source_url: str | None = None
    confidence: float = 0.5

    @property
    def full_name(self) -> str:
        return f"{self.given_name} {self.surname}".strip()

    @property
    def search_key(self) -> str:
        """Unique key for deduplication."""
        return f"{self.given_name}|{self.surname}|{self.birth_year or ''}|{self.birth_place or ''}"

    def estimated_census_years(self) -> list[int]:
        """Return census years this person would likely appear in based on birth/death."""
        if not self.birth_year:
            return CENSUS_YEARS[:5]  # Default to recent censuses

        years = []
        for cy in CENSUS_YEARS:
            age_at_census = cy - self.birth_year
            # Person must be born and alive
            if age_at_census >= 0:
                if self.death_year is None or cy <= self.death_year:
                    years.append(cy)
        return years


@dataclass
class CensusHousehold:
    """A household extracted from census data."""

    census_year: int
    location: str
    address: str | None = None
    head: CensusPerson | None = None
    members: list[CensusPerson] = field(default_factory=list)
    source_url: str | None = None

    def get_parents_of(self, person_name: str) -> list[CensusPerson]:
        """Find likely parents of a person in this household."""
        parents = []
        for member in self.members:
            rel = (member.relation_to_head or "").lower()
            if rel in ("head", "wife", "husband", "father", "mother"):
                # These are likely parents if person is a child
                for child in self.members:
                    child_rel = (child.relation_to_head or "").lower()
                    if child_rel in ("son", "daughter", "child") and person_name.lower() in child.full_name.lower():
                        parents.append(member)
                        break
        return parents

    def get_siblings_of(self, person_name: str) -> list[CensusPerson]:
        """Find siblings of a person in this household."""
        siblings = []
        for member in self.members:
            rel = (member.relation_to_head or "").lower()
            if rel in ("son", "daughter", "child"):
                if person_name.lower() not in member.full_name.lower():
                    siblings.append(member)
        return siblings


@dataclass
class FamilyTreeNode:
    """A node in the family tree."""

    person: CensusPerson
    father: FamilyTreeNode | None = None
    mother: FamilyTreeNode | None = None
    spouse: FamilyTreeNode | None = None
    children: list[FamilyTreeNode] = field(default_factory=list)
    siblings: list[FamilyTreeNode] = field(default_factory=list)
    census_records: list[CensusHousehold] = field(default_factory=list)
    generation: int = 0  # 0 = seed, 1 = parents, 2 = grandparents, etc.

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "person": {
                "name": self.person.full_name,
                "given_name": self.person.given_name,
                "surname": self.person.surname,
                "birth_year": self.person.birth_year,
                "birth_place": self.person.birth_place,
                "death_year": self.person.death_year,
                "death_place": self.person.death_place,
                "confidence": self.person.confidence,
            },
            "generation": self.generation,
            "census_records": [
                {
                    "year": h.census_year,
                    "location": h.location,
                    "address": h.address,
                    "source_url": h.source_url,
                }
                for h in self.census_records
            ],
        }

        if self.father:
            result["father"] = self.father.to_dict()
        if self.mother:
            result["mother"] = self.mother.to_dict()
        if self.spouse:
            result["spouse"] = self.spouse.to_dict()
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.siblings:
            result["siblings"] = [s.to_dict() for s in self.siblings]

        return result


class CensusTreeBuilder:
    """Builds family trees from census data and existing research."""

    def __init__(self, research_dir: Path | str = "research"):
        self.research_dir = Path(research_dir)
        self.visited: set[str] = set()
        self.tree_nodes: dict[str, FamilyTreeNode] = {}

    def load_existing_research(self, person_id: str) -> dict[str, Any] | None:
        """Load existing research profile for a person."""
        # Try common file patterns
        patterns = [
            self.research_dir / person_id / "profile.json",
            self.research_dir / f"{person_id}.json",
            self.research_dir / "profiles" / f"{person_id}.json",
        ]

        for path in patterns:
            if path.exists():
                try:
                    return json.loads(path.read_text())
                except Exception as e:
                    logger.warning("Failed to load %s: %s", path, e)

        return None

    def extract_family_from_profile(self, profile: dict[str, Any]) -> dict[str, list[CensusPerson]]:
        """Extract family members from a research profile."""
        family: dict[str, list[CensusPerson]] = {
            "parents": [],
            "siblings": [],
            "spouse": [],
            "children": [],
        }

        fam_data = profile.get("family", {})

        # Extract parents
        parents_data = fam_data.get("parents", {})

        father = parents_data.get("father", {})
        if father.get("given_name") or father.get("surname"):
            family["parents"].append(CensusPerson(
                given_name=father.get("given_name", ""),
                surname=father.get("surname", ""),
                birth_year=self._parse_year(father.get("birth_date") or father.get("birth_year")),
                birth_place=father.get("birth_place"),
                death_year=self._parse_year(father.get("death_date") or father.get("death_year")),
                death_place=father.get("death_place"),
                relation_to_head="head",
                source_url=father.get("source"),
                confidence=father.get("confidence", 0.7),
            ))

        mother = parents_data.get("mother", {})
        if mother.get("given_name") or mother.get("maiden_name") or mother.get("surname"):
            family["parents"].append(CensusPerson(
                given_name=mother.get("given_name", ""),
                surname=mother.get("maiden_name") or mother.get("surname", ""),
                birth_year=self._parse_year(mother.get("birth_date") or mother.get("birth_year")),
                birth_place=mother.get("birth_place"),
                relation_to_head="wife",
                source_url=mother.get("source"),
                confidence=mother.get("confidence", 0.7),
            ))

        # Extract siblings
        for sibling in fam_data.get("siblings", []):
            name_parts = (sibling.get("name", "") or "").split()
            if name_parts:
                family["siblings"].append(CensusPerson(
                    given_name=" ".join(name_parts[:-1]) if len(name_parts) > 1 else name_parts[0],
                    surname=name_parts[-1] if len(name_parts) > 1 else "",
                    birth_year=self._parse_year(sibling.get("birth_year") or sibling.get("birth_date")),
                    relation_to_head=sibling.get("relation", "sibling"),
                    confidence=sibling.get("confidence", 0.6),
                ))

        # Extract spouse
        spouse_data = fam_data.get("spouse")
        if spouse_data and isinstance(spouse_data, dict):
            name_parts = (spouse_data.get("name", "") or "").split()
            if name_parts:
                family["spouse"].append(CensusPerson(
                    given_name=" ".join(name_parts[:-1]) if len(name_parts) > 1 else name_parts[0],
                    surname=name_parts[-1] if len(name_parts) > 1 else "",
                    birth_year=self._parse_year(spouse_data.get("birth_year")),
                    confidence=spouse_data.get("confidence", 0.5),
                ))

        # Extract children
        children_data = fam_data.get("children", {})
        if isinstance(children_data, dict):
            for child in children_data.get("unverified_claims", []):
                name_parts = (child.get("name", "") or "").split()
                if name_parts:
                    family["children"].append(CensusPerson(
                        given_name=" ".join(name_parts[:-1]) if len(name_parts) > 1 else name_parts[0],
                        surname=name_parts[-1] if len(name_parts) > 1 else "",
                        confidence=child.get("confidence", 0.3),
                    ))

        return family

    def extract_census_sources(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract census source URLs from a profile."""
        census_sources = []

        for source in profile.get("sources", []):
            record_type = source.get("record_type", "")
            title = source.get("title", "").lower()

            if record_type == "census" or "census" in title:
                # Extract year from title
                year = None
                for y in CENSUS_YEARS:
                    if str(y) in title:
                        year = y
                        break

                census_sources.append({
                    "year": year,
                    "title": source.get("title"),
                    "url": source.get("url"),
                    "type": source.get("type", "primary"),
                })

        return census_sources

    def _parse_year(self, value: Any) -> int | None:
        """Parse a year from various formats."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            # Try to extract year from date string like "1892-07-25"
            if "-" in value:
                try:
                    return int(value.split("-")[0])
                except ValueError:
                    pass
            # Try direct conversion
            try:
                return int(value)
            except ValueError:
                pass
        return None

    def build_tree_from_profile(self, profile: dict[str, Any], max_generations: int = 3) -> FamilyTreeNode:
        """Build a family tree starting from a profile, working backwards through generations."""

        # Extract seed person from profile
        name_data = profile.get("name", {})
        birth_data = profile.get("birth", {})
        death_data = profile.get("death", {})

        seed = CensusPerson(
            given_name=name_data.get("given", ""),
            surname=name_data.get("surname", ""),
            birth_year=birth_data.get("year"),
            birth_place=birth_data.get("place_formatted") or birth_data.get("city"),
            death_year=death_data.get("year"),
            death_place=death_data.get("place"),
            confidence=birth_data.get("confidence", 0.9),
        )

        root = FamilyTreeNode(person=seed, generation=0)
        self.tree_nodes[seed.search_key] = root
        self.visited.add(seed.search_key)

        # Extract family from profile
        family = self.extract_family_from_profile(profile)

        # Add parents (generation 1)
        for parent in family["parents"]:
            if parent.search_key not in self.visited:
                self.visited.add(parent.search_key)
                parent_node = FamilyTreeNode(person=parent, generation=1)
                self.tree_nodes[parent.search_key] = parent_node

                if parent.relation_to_head in ("head", "father"):
                    root.father = parent_node
                elif parent.relation_to_head in ("wife", "mother"):
                    root.mother = parent_node

        # Add siblings (same generation as seed)
        for sibling in family["siblings"]:
            if sibling.search_key not in self.visited:
                self.visited.add(sibling.search_key)
                sibling_node = FamilyTreeNode(person=sibling, generation=0)
                self.tree_nodes[sibling.search_key] = sibling_node
                root.siblings.append(sibling_node)

        # Add census sources to root
        census_sources = self.extract_census_sources(profile)
        for cs in census_sources:
            if cs.get("year"):
                root.census_records.append(CensusHousehold(
                    census_year=cs["year"],
                    location=birth_data.get("place_formatted", ""),
                    source_url=cs.get("url"),
                ))

        return root

    def get_search_queue(self, root: FamilyTreeNode, max_generations: int = 3) -> list[tuple[CensusPerson, int, list[int]]]:
        """Get a queue of people to search for in censuses, working backwards.

        Returns: List of (person, generation, census_years_to_search)
        """
        queue: list[tuple[CensusPerson, int, list[int]]] = []

        def _add_to_queue(node: FamilyTreeNode | None, gen: int) -> None:
            if node is None or gen > max_generations:
                return

            person = node.person
            census_years = person.estimated_census_years()

            # Only add if we don't have census records for all years
            existing_years = {h.census_year for h in node.census_records}
            missing_years = [y for y in census_years if y not in existing_years]

            if missing_years:
                queue.append((person, gen, missing_years))

            # Recurse to parents (next generation back)
            _add_to_queue(node.father, gen + 1)
            _add_to_queue(node.mother, gen + 1)

        # Start with parents of seed (we already have seed's data)
        _add_to_queue(root.father, 1)
        _add_to_queue(root.mother, 1)

        return queue

    def export_tree(self, root: FamilyTreeNode, output_path: Path | str) -> None:
        """Export the family tree to JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        tree_data = {
            "root": root.to_dict(),
            "statistics": {
                "total_people": len(self.tree_nodes),
                "max_generation": max((n.generation for n in self.tree_nodes.values()), default=0),
                "people_by_generation": {},
            },
        }

        # Count by generation
        for node in self.tree_nodes.values():
            gen = node.generation
            tree_data["statistics"]["people_by_generation"][str(gen)] = \
                tree_data["statistics"]["people_by_generation"].get(str(gen), 0) + 1

        output_path.write_text(json.dumps(tree_data, indent=2))
        logger.info("Exported family tree to %s", output_path)


def build_census_tree_from_research(
    person_id: str,
    research_dir: str = "research",
    output_path: str | None = None,
    max_generations: int = 3,
) -> dict[str, Any]:
    """Build a census-based family tree from existing research.

    Args:
        person_id: The person identifier (e.g., "archer-l-durham")
        research_dir: Directory containing research files
        output_path: Where to save the tree (default: research/trees/{person_id}/census_tree.json)
        max_generations: How many generations back to search

    Returns:
        Dictionary with tree data and search queue for further research
    """
    builder = CensusTreeBuilder(research_dir)

    # Load existing research
    profile = builder.load_existing_research(person_id)
    if not profile:
        return {
            "error": f"No research profile found for {person_id}",
            "searched_paths": [
                str(builder.research_dir / person_id / "profile.json"),
                str(builder.research_dir / f"{person_id}.json"),
            ],
        }

    # Build tree from profile
    root = builder.build_tree_from_profile(profile, max_generations)

    # Get search queue for missing census data
    search_queue = builder.get_search_queue(root, max_generations)

    # Export tree
    if output_path is None:
        output_path = f"research/trees/{person_id}/census_tree.json"
    builder.export_tree(root, output_path)

    return {
        "tree_file": output_path,
        "people_found": len(builder.tree_nodes),
        "search_queue": [
            {
                "name": p.full_name,
                "birth_year": p.birth_year,
                "birth_place": p.birth_place,
                "generation": gen,
                "census_years_to_search": years,
            }
            for p, gen, years in search_queue
        ],
        "family_summary": {
            "seed": root.person.full_name,
            "father": root.father.person.full_name if root.father else None,
            "mother": root.mother.person.full_name if root.mother else None,
            "siblings": [s.person.full_name for s in root.siblings],
        },
    }
