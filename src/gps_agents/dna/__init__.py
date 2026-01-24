"""DNA analysis utilities for genealogical research.

This module provides:
- DNA match analysis and relationship estimation
- Haplogroup interpretation
- Ethnicity estimate parsing
- Shared segment analysis
- DNA match clustering

IMPORTANT: DNA results are PROBABILISTIC and should not override documentary evidence.
All interpretations include appropriate caveats and confidence intervals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DNATestProvider(Enum):
    """DNA testing companies."""

    ANCESTRY = "AncestryDNA"
    TWENTYTHREE = "23andMe"
    MYHERITAGE = "MyHeritage"
    FTDNA = "FamilyTreeDNA"
    GEDMATCH = "GEDmatch"
    LIVINGDNA = "LivingDNA"
    UNKNOWN = "Unknown"


class HaplogroupType(Enum):
    """Types of haplogroups."""

    MTDNA = "mtDNA"  # Maternal line
    YDNA = "Y-DNA"  # Paternal line (males only)


@dataclass
class EthnicityEstimate:
    """Ethnicity estimate from DNA testing.

    Note: Percentages are estimates with confidence intervals.
    They reflect genetic similarity to reference populations,
    NOT necessarily actual ancestry.
    """

    region: str
    percentage: float
    confidence_low: float = 0.0
    confidence_high: float = 0.0
    provider: DNATestProvider = DNATestProvider.UNKNOWN
    sub_regions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HaplogroupResult:
    """Haplogroup result from DNA testing.

    Haplogroups trace maternal (mtDNA) or paternal (Y-DNA) lines
    back thousands of years to ancient population groups.
    """

    haplogroup: str
    haplogroup_type: HaplogroupType
    terminal_snp: str | None = None
    confidence: float = 1.0
    migration_path: list[str] = field(default_factory=list)
    geographic_origin: str | None = None
    time_estimate_years: tuple[int, int] | None = None  # (min, max) years ago


@dataclass
class DNAMatch:
    """A DNA match from autosomal testing.

    cM (centimorgans) measures genetic similarity.
    Larger cM = closer relationship.
    """

    match_name: str
    shared_cm: float
    shared_segments: int = 0
    largest_segment_cm: float = 0.0
    provider: DNATestProvider = DNATestProvider.UNKNOWN
    predicted_relationship: str | None = None
    common_ancestors: list[str] = field(default_factory=list)
    shared_matches: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class RelationshipEstimate:
    """Estimated relationship based on shared DNA.

    Always includes multiple possibilities and confidence levels.
    """

    possible_relationships: list[str]
    generations_to_mrca: tuple[int, int]  # (min, max) generations to Most Recent Common Ancestor
    probability: float = 0.0  # If calculable
    confidence: str = "low"  # low, medium, high
    caveats: list[str] = field(default_factory=list)


# Standard cM ranges for relationship estimation
# Based on empirical data from DNA testing companies
CM_RELATIONSHIP_RANGES = {
    # (min_cm, max_cm): [(relationship, probability)]
    (3400, 3720): [("identical twin", 0.99)],
    (2200, 3720): [("full sibling", 0.70), ("parent/child", 0.30)],
    (1300, 2300): [("grandparent/grandchild", 0.40), ("aunt/uncle", 0.30), ("half-sibling", 0.30)],
    (550, 1300): [("1st cousin", 0.50), ("great-grandparent", 0.20), ("great-aunt/uncle", 0.30)],
    (200, 620): [("2nd cousin", 0.40), ("1st cousin once removed", 0.35), ("half 1st cousin", 0.25)],
    (45, 230): [("3rd cousin", 0.45), ("2nd cousin once removed", 0.35), ("1st cousin twice removed", 0.20)],
    (15, 78): [("4th cousin", 0.50), ("3rd cousin once removed", 0.30), ("distant cousin", 0.20)],
    (0, 20): [("5th+ cousin", 0.60), ("distant relative", 0.30), ("possible noise", 0.10)],
}


def estimate_relationship(shared_cm: float, shared_segments: int = 0) -> RelationshipEstimate:
    """Estimate relationship based on shared DNA.

    Args:
        shared_cm: Centimorgans shared
        shared_segments: Number of shared segments (optional)

    Returns:
        RelationshipEstimate with possible relationships and caveats
    """
    possibilities: list[str] = []
    generations = (0, 0)

    for (min_cm, max_cm), relationships in CM_RELATIONSHIP_RANGES.items():
        if min_cm <= shared_cm <= max_cm:
            for rel, prob in relationships:
                possibilities.append(f"{rel} ({prob*100:.0f}% likely)")

            # Estimate generations
            if shared_cm > 2200:
                generations = (0, 1)
            elif shared_cm > 1300:
                generations = (1, 2)
            elif shared_cm > 550:
                generations = (2, 3)
            elif shared_cm > 200:
                generations = (3, 4)
            elif shared_cm > 45:
                generations = (4, 5)
            else:
                generations = (5, 10)
            break

    if not possibilities:
        if shared_cm > 3720:
            possibilities = ["Possible identical twin or data issue"]
            generations = (0, 0)
        else:
            possibilities = ["Very distant relative or genealogical noise"]
            generations = (7, 15)

    caveats = [
        "DNA relationship estimates have wide ranges",
        "Multiple relationship types can produce similar cM values",
        "Endogamy (intermarriage) can inflate shared DNA",
        "Documentary evidence required to confirm actual relationship",
    ]

    if shared_segments and shared_segments < 4:
        caveats.append(f"Low segment count ({shared_segments}) may indicate noise or very distant relationship")

    return RelationshipEstimate(
        possible_relationships=possibilities,
        generations_to_mrca=generations,
        confidence="medium" if 100 < shared_cm < 1500 else "low",
        caveats=caveats,
    )


def parse_ethnicity_estimates(
    raw_data: dict[str, Any],
    provider: DNATestProvider = DNATestProvider.UNKNOWN,
) -> list[EthnicityEstimate]:
    """Parse ethnicity estimates from various providers.

    Args:
        raw_data: Raw ethnicity data from provider
        provider: DNA testing provider

    Returns:
        List of standardized EthnicityEstimate objects
    """
    estimates: list[EthnicityEstimate] = []

    # Handle different provider formats
    if provider == DNATestProvider.ANCESTRY:
        for region_data in raw_data.get("ethnicityRegions", []):
            estimates.append(EthnicityEstimate(
                region=region_data.get("ethnicity", "Unknown"),
                percentage=region_data.get("percent", 0),
                confidence_low=region_data.get("range", {}).get("low", 0),
                confidence_high=region_data.get("range", {}).get("high", 0),
                provider=provider,
            ))

    elif provider == DNATestProvider.TWENTYTHREE:
        for region, percentage in raw_data.get("ancestry_composition", {}).items():
            if isinstance(percentage, dict):
                pct = percentage.get("percentage", 0)
            else:
                pct = percentage
            estimates.append(EthnicityEstimate(
                region=region,
                percentage=pct,
                provider=provider,
            ))

    elif provider == DNATestProvider.MYHERITAGE:
        for ethnic in raw_data.get("ethnicities", []):
            estimates.append(EthnicityEstimate(
                region=ethnic.get("name", "Unknown"),
                percentage=ethnic.get("percentage", 0),
                provider=provider,
            ))

    else:
        # Generic format
        for region, value in raw_data.items():
            if isinstance(value, (int, float)):
                estimates.append(EthnicityEstimate(
                    region=region,
                    percentage=float(value),
                    provider=provider,
                ))

    return estimates


def interpret_haplogroup(haplogroup: str, haplogroup_type: HaplogroupType) -> HaplogroupResult:
    """Interpret a haplogroup result.

    Args:
        haplogroup: Haplogroup designation (e.g., "R1b-M269", "H1a1")
        haplogroup_type: mtDNA or Y-DNA

    Returns:
        HaplogroupResult with interpretation
    """
    # Major haplogroup origins (simplified)
    MTDNA_ORIGINS = {
        "H": ("Western Europe", ["Africa", "Near East", "Europe"]),
        "U": ("Europe/Near East", ["Africa", "Near East", "Europe"]),
        "K": ("Near East", ["Africa", "Near East", "Europe"]),
        "J": ("Near East", ["Africa", "Near East", "Mediterranean"]),
        "T": ("Near East", ["Africa", "Near East", "Europe"]),
        "V": ("Iberia/Western Europe", ["Africa", "Near East", "Iberia"]),
        "I": ("Western Europe", ["Africa", "Near East", "Northern Europe"]),
        "W": ("Near East", ["Africa", "Near East", "Europe"]),
        "X": ("Near East/Americas", ["Africa", "Near East", "Europe/Americas"]),
        "A": ("East Asia/Americas", ["Africa", "Asia", "Beringia", "Americas"]),
        "B": ("East Asia/Americas", ["Africa", "Asia", "Beringia", "Americas"]),
        "C": ("East Asia/Americas", ["Africa", "Asia", "Beringia", "Americas"]),
        "D": ("East Asia/Americas", ["Africa", "Asia", "Beringia", "Americas"]),
        "L": ("Africa", ["Africa"]),
        "M": ("South Asia", ["Africa", "South Asia"]),
        "N": ("Near East/East Asia", ["Africa", "Near East", "Asia"]),
    }

    YDNA_ORIGINS = {
        "R1b": ("Western Europe", ["Africa", "Near East", "Europe"], (4500, 10000)),
        "R1a": ("Eastern Europe/Central Asia", ["Africa", "Near East", "Eurasia"], (4500, 10000)),
        "I1": ("Northern Europe", ["Africa", "Near East", "Northern Europe"], (4500, 8000)),
        "I2": ("Western/Southeastern Europe", ["Africa", "Near East", "Europe"], (10000, 25000)),
        "J1": ("Near East/Arabia", ["Africa", "Near East"], (10000, 20000)),
        "J2": ("Near East/Mediterranean", ["Africa", "Near East", "Mediterranean"], (15000, 25000)),
        "E1b1b": ("Africa/Mediterranean", ["Africa", "Near East", "Mediterranean"], (20000, 35000)),
        "G": ("Near East/Caucasus", ["Africa", "Near East", "Caucasus"], (15000, 25000)),
        "N": ("Northern Eurasia", ["Africa", "Near East", "Northern Asia"], (10000, 20000)),
        "O": ("East Asia", ["Africa", "Asia"], (20000, 35000)),
        "Q": ("Central Asia/Americas", ["Africa", "Asia", "Beringia", "Americas"], (15000, 25000)),
    }

    # Extract major haplogroup letter(s)
    major = haplogroup.upper().split("-")[0].rstrip("0123456789")
    if not major:
        major = haplogroup[0].upper() if haplogroup else "?"

    origin = None
    path: list[str] = []
    time_range = None

    if haplogroup_type == HaplogroupType.MTDNA:
        if major in MTDNA_ORIGINS:
            origin, path = MTDNA_ORIGINS[major]
    else:
        # Y-DNA - check longer prefixes first
        for prefix in sorted(YDNA_ORIGINS.keys(), key=len, reverse=True):
            if major.startswith(prefix.upper()):
                origin, path, time_range = YDNA_ORIGINS[prefix]
                break

    return HaplogroupResult(
        haplogroup=haplogroup,
        haplogroup_type=haplogroup_type,
        terminal_snp=haplogroup.split("-")[1] if "-" in haplogroup else None,
        geographic_origin=origin,
        migration_path=path,
        time_estimate_years=time_range,
    )


def cluster_dna_matches(
    matches: list[DNAMatch],
    threshold_cm: float = 30.0,
) -> list[list[DNAMatch]]:
    """Cluster DNA matches by shared matches (Leeds Method).

    The Leeds Method groups DNA matches who share DNA with each other,
    helping identify distinct ancestral lines.

    Args:
        matches: List of DNA matches
        threshold_cm: Minimum cM for clustering

    Returns:
        List of clusters (each cluster = list of related matches)
    """
    # Filter matches above threshold
    significant = [m for m in matches if m.shared_cm >= threshold_cm]

    if not significant:
        return []

    # Build adjacency based on shared matches
    clusters: list[set[str]] = []
    match_to_cluster: dict[str, int] = {}

    for match in significant:
        shared = set(match.shared_matches)
        shared.add(match.match_name)

        # Find existing clusters that overlap
        overlapping = []
        for i, cluster in enumerate(clusters):
            if cluster & shared:
                overlapping.append(i)

        if not overlapping:
            # New cluster
            new_cluster = shared
            clusters.append(new_cluster)
            for name in new_cluster:
                match_to_cluster[name] = len(clusters) - 1
        elif len(overlapping) == 1:
            # Add to existing cluster
            clusters[overlapping[0]].update(shared)
            for name in shared:
                match_to_cluster[name] = overlapping[0]
        else:
            # Merge clusters
            merged = set()
            for i in overlapping:
                merged.update(clusters[i])
            merged.update(shared)

            # Remove old clusters (in reverse order)
            for i in sorted(overlapping, reverse=True):
                clusters.pop(i)

            clusters.append(merged)
            for name in merged:
                match_to_cluster[name] = len(clusters) - 1

    # Convert back to DNAMatch objects
    result: list[list[DNAMatch]] = []
    for cluster_names in clusters:
        cluster_matches = [m for m in significant if m.match_name in cluster_names]
        if cluster_matches:
            result.append(sorted(cluster_matches, key=lambda m: m.shared_cm, reverse=True))

    return result


__all__ = [
    "DNATestProvider",
    "HaplogroupType",
    "EthnicityEstimate",
    "HaplogroupResult",
    "DNAMatch",
    "RelationshipEstimate",
    "CM_RELATIONSHIP_RANGES",
    "estimate_relationship",
    "parse_ethnicity_estimates",
    "interpret_haplogroup",
    "cluster_dna_matches",
]
