"""Graph Storage for genealogical relationships.

Provides a graph abstraction layer that supports:
- Neo4j for production (relationship traversal, Cypher queries)
- RocksDB fallback for development/testing
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

__all__ = [
    "GraphStore",
    "Neo4jGraphStore",
    "RocksDBGraphStore",
    "Node",
    "Edge",
    "NodeType",
    "EdgeType",
    "GraphQuery",
    "PathResult",
]
