"""Graph Storage for genealogical relationships.

Provides a graph abstraction layer that supports:
- Neo4j for production (relationship traversal, Cypher queries)
- RocksDB fallback for development/testing
- CQRS projection layer for syncing ledger to graph
- Pedigree traversal queries (ancestors, descendants, kinship)
"""
from .graph_store import (
    Edge,
    EdgeType,
    GraphQuery,
    GraphStore,
    Neo4jGraphStore,
    Node,
    NodeType,
    PathResult,
    RocksDBGraphStore,
)
from .models import (
    AncestorResult,
    DescendantResult,
    FamilyUnit,
    FamilyUnitQuery,
    KinshipQuery,
    KinshipResult,
    PedigreeQuery,
    PedigreeResult,
    PersonSummary,
    ProjectionMetadata,
    ProjectionStatus,
    RelationshipType,
    SyncEvent,
    TraversalDirection,
)
from .projection import (
    EvidenceProjector,
    GraphProjection,
    PersonProjector,
    ProjectionSyncError,
)
from .traversal import (
    Neo4jPedigreeTraversal,
    PedigreeTraversal,
)

__all__ = [
    # Core graph store
    "GraphStore",
    "Neo4jGraphStore",
    "RocksDBGraphStore",
    "Node",
    "Edge",
    "NodeType",
    "EdgeType",
    "GraphQuery",
    "PathResult",
    # Pedigree models
    "PersonSummary",
    "AncestorResult",
    "DescendantResult",
    "KinshipResult",
    "FamilyUnit",
    "PedigreeQuery",
    "KinshipQuery",
    "FamilyUnitQuery",
    "PedigreeResult",
    "RelationshipType",
    "TraversalDirection",
    # CQRS projection
    "GraphProjection",
    "PersonProjector",
    "EvidenceProjector",
    "ProjectionSyncError",
    "ProjectionMetadata",
    "ProjectionStatus",
    "SyncEvent",
    # Traversal
    "PedigreeTraversal",
    "Neo4jPedigreeTraversal",
]
