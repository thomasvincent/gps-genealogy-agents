"""High-Scale Probabilistic Linkage module for GPS-compliant entity resolution.

This module provides entity resolution using Splink (probabilistic record linkage)
to handle historical name variants, OCR errors, and ambiguous matches at scale.

Key Components:
- SplinkEntityResolver: Core entity resolution using Fellegi-Sunter model
- LinkageResult: Typed wrapper for linkage decisions with provenance
- ComparisonConfig: GPS-compliant comparison configurations

Australian Bureau of Statistics uses Splink for 2026 Census linking.

Example:
    >>> from gps_agents.genealogy_crawler.linkage import (
    ...     SplinkEntityResolver,
    ...     CensusComparisonConfig,
    ... )
    >>>
    >>> resolver = SplinkEntityResolver(
    ...     comparison_config=CensusComparisonConfig(),
    ...     threshold=0.85,
    ... )
    >>>
    >>> clusters = await resolver.resolve(extracted_persons)
    >>> for cluster in clusters:
    ...     print(f"Cluster {cluster.cluster_id}: {cluster.canonical_name}")
"""
from .models import (
    ClusterDecision,
    ComparisonType,
    EntityCluster,
    FeatureComparison,
    LinkageDecision,
    LinkageProvenance,
    LinkageResult,
    MatchCandidate,
    MatchConfidence,
)
from .configs import (
    BaseComparisonConfig,
    CensusComparisonConfig,
    VitalRecordComparisonConfig,
)
from .resolver import SplinkEntityResolver

__all__ = [
    # Models - Enums
    "ComparisonType",
    "MatchConfidence",
    "ClusterDecision",
    # Models - Data
    "FeatureComparison",
    "MatchCandidate",
    "LinkageProvenance",
    "LinkageDecision",
    "EntityCluster",
    "LinkageResult",
    # Configs
    "BaseComparisonConfig",
    "CensusComparisonConfig",
    "VitalRecordComparisonConfig",
    # Resolver
    "SplinkEntityResolver",
]
