"""Graph Storage implementation for genealogical relationships.

Supports Neo4j for production and RocksDB for development/testing.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None  # type: ignore

try:
    import rocksdb
except ImportError:
    rocksdb = None  # type: ignore

if TYPE_CHECKING:
    from collections.abc import Iterator


class NodeType(str, Enum):
    """Types of nodes in the genealogical graph."""
    PERSON = "Person"
    EVENT = "Event"
    PLACE = "Place"
    SOURCE = "Source"
    ASSERTION = "Assertion"


class EdgeType(str, Enum):
    """Types of edges (relationships) in the genealogical graph."""
    # Family relationships
    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"
    SPOUSE_OF = "SPOUSE_OF"
    SIBLING_OF = "SIBLING_OF"

    # Event participation
    PARTICIPATED_IN = "PARTICIPATED_IN"
    WITNESSED = "WITNESSED"

    # Location
    BORN_AT = "BORN_AT"
    DIED_AT = "DIED_AT"
    RESIDED_AT = "RESIDED_AT"
    BURIED_AT = "BURIED_AT"

    # Evidence
    SUPPORTED_BY = "SUPPORTED_BY"
    CITED_IN = "CITED_IN"
    EXTRACTED_FROM = "EXTRACTED_FROM"

    # Merge candidates
    POSSIBLY_SAME_AS = "POSSIBLY_SAME_AS"
    CONFIRMED_SAME_AS = "CONFIRMED_SAME_AS"


@dataclass
class Node:
    """A node in the genealogical graph."""
    node_id: UUID = field(default_factory=uuid4)
    node_type: NodeType = NodeType.PERSON
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "node_id": str(self.node_id),
            "node_type": self.node_type.value,
            "properties": self.properties,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Node:
        """Deserialize from dictionary."""
        return cls(
            node_id=UUID(data["node_id"]),
            node_type=NodeType(data["node_type"]),
            properties=data.get("properties", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(UTC),
        )


@dataclass
class Edge:
    """An edge (relationship) in the genealogical graph."""
    edge_id: UUID = field(default_factory=uuid4)
    edge_type: EdgeType = EdgeType.PARENT_OF
    source_id: UUID = field(default_factory=uuid4)
    target_id: UUID = field(default_factory=uuid4)
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "edge_id": str(self.edge_id),
            "edge_type": self.edge_type.value,
            "source_id": str(self.source_id),
            "target_id": str(self.target_id),
            "properties": self.properties,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Edge:
        """Deserialize from dictionary."""
        return cls(
            edge_id=UUID(data["edge_id"]),
            edge_type=EdgeType(data["edge_type"]),
            source_id=UUID(data["source_id"]),
            target_id=UUID(data["target_id"]),
            properties=data.get("properties", {}),
            confidence=data.get("confidence", 1.0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC),
        )


@dataclass
class PathResult:
    """Result of a path query."""
    nodes: list[Node]
    edges: list[Edge]
    length: int

    @property
    def node_ids(self) -> list[UUID]:
        """Get list of node IDs in the path."""
        return [n.node_id for n in self.nodes]


@dataclass
class GraphQuery:
    """A query to execute against the graph."""
    # Node filters
    node_type: NodeType | None = None
    node_properties: dict[str, Any] = field(default_factory=dict)

    # Edge filters
    edge_types: list[EdgeType] = field(default_factory=list)
    min_confidence: float = 0.0

    # Traversal
    start_node_id: UUID | None = None
    max_depth: int = 3
    direction: str = "both"  # "outgoing", "incoming", "both"

    # Pagination
    limit: int = 100
    offset: int = 0


class GraphStore(ABC):
    """Abstract base class for graph storage."""

    @abstractmethod
    def add_node(self, node: Node) -> Node:
        """Add a node to the graph."""
        ...

    @abstractmethod
    def get_node(self, node_id: UUID) -> Node | None:
        """Get a node by ID."""
        ...

    @abstractmethod
    def update_node(self, node: Node) -> Node:
        """Update an existing node."""
        ...

    @abstractmethod
    def delete_node(self, node_id: UUID) -> bool:
        """Delete a node and its edges."""
        ...

    @abstractmethod
    def add_edge(self, edge: Edge) -> Edge:
        """Add an edge to the graph."""
        ...

    @abstractmethod
    def get_edge(self, edge_id: UUID) -> Edge | None:
        """Get an edge by ID."""
        ...

    @abstractmethod
    def delete_edge(self, edge_id: UUID) -> bool:
        """Delete an edge."""
        ...

    @abstractmethod
    def get_neighbors(
        self,
        node_id: UUID,
        edge_types: list[EdgeType] | None = None,
        direction: str = "both",
    ) -> list[tuple[Edge, Node]]:
        """Get neighboring nodes with their edges."""
        ...

    @abstractmethod
    def find_path(
        self,
        start_id: UUID,
        end_id: UUID,
        max_depth: int = 5,
        edge_types: list[EdgeType] | None = None,
    ) -> PathResult | None:
        """Find shortest path between two nodes."""
        ...

    @abstractmethod
    def query(self, query: GraphQuery) -> list[Node]:
        """Execute a graph query."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""
        ...


class Neo4jGraphStore(GraphStore):
    """Neo4j-backed graph storage.

    Uses Cypher queries for efficient relationship traversal.
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str = "password",
        database: str = "genealogy",
    ) -> None:
        if GraphDatabase is None:
            raise ImportError("neo4j package required: pip install neo4j")

        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database

    def add_node(self, node: Node) -> Node:
        """Add a node to Neo4j."""
        with self.driver.session(database=self.database) as session:
            props = {
                "node_id": str(node.node_id),
                **node.properties,
                "created_at": node.created_at.isoformat(),
                "updated_at": node.updated_at.isoformat(),
            }

            session.run(
                f"""
                CREATE (n:{node.node_type.value} $props)
                """,
                props=props,
            )

        return node

    def get_node(self, node_id: UUID) -> Node | None:
        """Get a node by ID from Neo4j."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (n {node_id: $node_id})
                RETURN n, labels(n) as labels
                """,
                node_id=str(node_id),
            )

            record = result.single()
            if record is None:
                return None

            neo_node = record["n"]
            labels = record["labels"]

            node_type = NodeType(labels[0]) if labels else NodeType.PERSON

            props = dict(neo_node)
            node_id_str = props.pop("node_id")
            created_at = props.pop("created_at", None)
            updated_at = props.pop("updated_at", None)

            return Node(
                node_id=UUID(node_id_str),
                node_type=node_type,
                properties=props,
                created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(UTC),
                updated_at=datetime.fromisoformat(updated_at) if updated_at else datetime.now(UTC),
            )

    def update_node(self, node: Node) -> Node:
        """Update a node in Neo4j."""
        node.updated_at = datetime.now(UTC)

        with self.driver.session(database=self.database) as session:
            props = {
                **node.properties,
                "updated_at": node.updated_at.isoformat(),
            }

            session.run(
                """
                MATCH (n {node_id: $node_id})
                SET n += $props
                """,
                node_id=str(node.node_id),
                props=props,
            )

        return node

    def delete_node(self, node_id: UUID) -> bool:
        """Delete a node and its edges from Neo4j."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (n {node_id: $node_id})
                DETACH DELETE n
                RETURN count(n) as deleted
                """,
                node_id=str(node_id),
            )

            record = result.single()
            return record["deleted"] > 0 if record else False

    def add_edge(self, edge: Edge) -> Edge:
        """Add an edge to Neo4j."""
        with self.driver.session(database=self.database) as session:
            props = {
                "edge_id": str(edge.edge_id),
                **edge.properties,
                "confidence": edge.confidence,
                "created_at": edge.created_at.isoformat(),
            }

            session.run(
                f"""
                MATCH (a {{node_id: $source_id}})
                MATCH (b {{node_id: $target_id}})
                CREATE (a)-[r:{edge.edge_type.value} $props]->(b)
                """,
                source_id=str(edge.source_id),
                target_id=str(edge.target_id),
                props=props,
            )

        return edge

    def get_edge(self, edge_id: UUID) -> Edge | None:
        """Get an edge by ID from Neo4j."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (a)-[r {edge_id: $edge_id}]->(b)
                RETURN r, type(r) as edge_type, a.node_id as source_id, b.node_id as target_id
                """,
                edge_id=str(edge_id),
            )

            record = result.single()
            if record is None:
                return None

            neo_rel = record["r"]
            props = dict(neo_rel)
            edge_id_str = props.pop("edge_id")
            confidence = props.pop("confidence", 1.0)
            created_at = props.pop("created_at", None)

            return Edge(
                edge_id=UUID(edge_id_str),
                edge_type=EdgeType(record["edge_type"]),
                source_id=UUID(record["source_id"]),
                target_id=UUID(record["target_id"]),
                properties=props,
                confidence=confidence,
                created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(UTC),
            )

    def delete_edge(self, edge_id: UUID) -> bool:
        """Delete an edge from Neo4j."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH ()-[r {edge_id: $edge_id}]->()
                DELETE r
                RETURN count(r) as deleted
                """,
                edge_id=str(edge_id),
            )

            record = result.single()
            return record["deleted"] > 0 if record else False

    def get_neighbors(
        self,
        node_id: UUID,
        edge_types: list[EdgeType] | None = None,
        direction: str = "both",
    ) -> list[tuple[Edge, Node]]:
        """Get neighboring nodes from Neo4j."""
        # Build relationship pattern
        if edge_types:
            rel_types = "|".join(et.value for et in edge_types)
            rel_pattern = f"[r:{rel_types}]"
        else:
            rel_pattern = "[r]"

        # Build direction pattern
        if direction == "outgoing":
            pattern = f"(n)-{rel_pattern}->(m)"
        elif direction == "incoming":
            pattern = f"(n)<-{rel_pattern}-(m)"
        else:
            pattern = f"(n)-{rel_pattern}-(m)"

        with self.driver.session(database=self.database) as session:
            result = session.run(
                f"""
                MATCH {pattern}
                WHERE n.node_id = $node_id
                RETURN r, type(r) as edge_type, startNode(r).node_id as source_id,
                       endNode(r).node_id as target_id, m, labels(m) as labels
                """,
                node_id=str(node_id),
            )

            neighbors = []
            for record in result:
                neo_rel = record["r"]
                neo_node = record["m"]
                labels = record["labels"]

                rel_props = dict(neo_rel)
                edge_id_str = rel_props.pop("edge_id", str(uuid4()))
                confidence = rel_props.pop("confidence", 1.0)
                created_at = rel_props.pop("created_at", None)

                edge = Edge(
                    edge_id=UUID(edge_id_str),
                    edge_type=EdgeType(record["edge_type"]),
                    source_id=UUID(record["source_id"]),
                    target_id=UUID(record["target_id"]),
                    properties=rel_props,
                    confidence=confidence,
                    created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(UTC),
                )

                node_props = dict(neo_node)
                node_id_str = node_props.pop("node_id")
                node_created_at = node_props.pop("created_at", None)
                node_updated_at = node_props.pop("updated_at", None)

                node = Node(
                    node_id=UUID(node_id_str),
                    node_type=NodeType(labels[0]) if labels else NodeType.PERSON,
                    properties=node_props,
                    created_at=datetime.fromisoformat(node_created_at) if node_created_at else datetime.now(UTC),
                    updated_at=datetime.fromisoformat(node_updated_at) if node_updated_at else datetime.now(UTC),
                )

                neighbors.append((edge, node))

            return neighbors

    def find_path(
        self,
        start_id: UUID,
        end_id: UUID,
        max_depth: int = 5,
        edge_types: list[EdgeType] | None = None,
    ) -> PathResult | None:
        """Find shortest path between two nodes in Neo4j."""
        if edge_types:
            rel_types = "|".join(et.value for et in edge_types)
            rel_pattern = f"[*1..{max_depth}]"
        else:
            rel_pattern = f"[*1..{max_depth}]"

        with self.driver.session(database=self.database) as session:
            result = session.run(
                f"""
                MATCH p = shortestPath((a {{node_id: $start_id}})-{rel_pattern}-(b {{node_id: $end_id}}))
                RETURN nodes(p) as path_nodes, relationships(p) as path_rels
                """,
                start_id=str(start_id),
                end_id=str(end_id),
            )

            record = result.single()
            if record is None:
                return None

            nodes = []
            for neo_node in record["path_nodes"]:
                props = dict(neo_node)
                node_id_str = props.pop("node_id")
                created_at = props.pop("created_at", None)
                updated_at = props.pop("updated_at", None)

                nodes.append(Node(
                    node_id=UUID(node_id_str),
                    node_type=NodeType.PERSON,  # Would need labels for accurate type
                    properties=props,
                    created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(UTC),
                    updated_at=datetime.fromisoformat(updated_at) if updated_at else datetime.now(UTC),
                ))

            edges = []
            for neo_rel in record["path_rels"]:
                props = dict(neo_rel)
                edge_id_str = props.pop("edge_id", str(uuid4()))
                confidence = props.pop("confidence", 1.0)
                created_at = props.pop("created_at", None)

                edges.append(Edge(
                    edge_id=UUID(edge_id_str),
                    edge_type=EdgeType.PARENT_OF,  # Would need type() for accurate type
                    source_id=nodes[0].node_id,  # Simplified
                    target_id=nodes[-1].node_id,
                    properties=props,
                    confidence=confidence,
                    created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(UTC),
                ))

            return PathResult(nodes=nodes, edges=edges, length=len(edges))

    def query(self, query: GraphQuery) -> list[Node]:
        """Execute a graph query on Neo4j."""
        with self.driver.session(database=self.database) as session:
            # Build match clause
            if query.node_type:
                match_clause = f"MATCH (n:{query.node_type.value})"
            else:
                match_clause = "MATCH (n)"

            # Build where clause
            where_clauses = []
            params = {}

            for key, value in query.node_properties.items():
                where_clauses.append(f"n.{key} = ${key}")
                params[key] = value

            where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"

            result = session.run(
                f"""
                {match_clause}
                WHERE {where_clause}
                RETURN n, labels(n) as labels
                SKIP $offset LIMIT $limit
                """,
                **params,
                offset=query.offset,
                limit=query.limit,
            )

            nodes = []
            for record in result:
                neo_node = record["n"]
                labels = record["labels"]

                props = dict(neo_node)
                node_id_str = props.pop("node_id")
                created_at = props.pop("created_at", None)
                updated_at = props.pop("updated_at", None)

                nodes.append(Node(
                    node_id=UUID(node_id_str),
                    node_type=NodeType(labels[0]) if labels else NodeType.PERSON,
                    properties=props,
                    created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(UTC),
                    updated_at=datetime.fromisoformat(updated_at) if updated_at else datetime.now(UTC),
                ))

            return nodes

    def close(self) -> None:
        """Close the Neo4j driver."""
        self.driver.close()


class RocksDBGraphStore(GraphStore):
    """RocksDB-backed graph storage for development/testing.

    Uses adjacency lists stored in RocksDB with key prefixes:
    - "node:{node_id}" -> Node data
    - "edge:{edge_id}" -> Edge data
    - "adj:out:{node_id}:{edge_type}:{target_id}" -> outgoing edge reference
    - "adj:in:{node_id}:{edge_type}:{source_id}" -> incoming edge reference
    """

    NODE_PREFIX = b"node:"
    EDGE_PREFIX = b"edge:"
    ADJ_OUT_PREFIX = b"adj:out:"
    ADJ_IN_PREFIX = b"adj:in:"

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)

        if rocksdb is None:
            # In-memory fallback
            self._use_fallback = True
            self._nodes: dict[str, Node] = {}
            self._edges: dict[str, Edge] = {}
            self._adj_out: dict[str, set[str]] = {}  # node_id -> set of edge_ids
            self._adj_in: dict[str, set[str]] = {}   # node_id -> set of edge_ids
        else:
            self._use_fallback = False
            opts = rocksdb.Options()
            opts.create_if_missing = True
            opts.max_open_files = 300
            self.db = rocksdb.DB(str(self.db_path / "graph.db"), opts)

    def add_node(self, node: Node) -> Node:
        """Add a node to the graph."""
        node_key = str(node.node_id)
        node_data = json.dumps(node.to_dict()).encode()

        if self._use_fallback:
            self._nodes[node_key] = node
            if node_key not in self._adj_out:
                self._adj_out[node_key] = set()
            if node_key not in self._adj_in:
                self._adj_in[node_key] = set()
        else:
            self.db.put(self.NODE_PREFIX + node_key.encode(), node_data)

        return node

    def get_node(self, node_id: UUID) -> Node | None:
        """Get a node by ID."""
        node_key = str(node_id)

        if self._use_fallback:
            return self._nodes.get(node_key)

        node_data = self.db.get(self.NODE_PREFIX + node_key.encode())
        if node_data is None:
            return None

        return Node.from_dict(json.loads(node_data.decode()))

    def update_node(self, node: Node) -> Node:
        """Update an existing node."""
        node.updated_at = datetime.now(UTC)
        return self.add_node(node)

    def delete_node(self, node_id: UUID) -> bool:
        """Delete a node and its edges."""
        node_key = str(node_id)

        if self._use_fallback:
            if node_key not in self._nodes:
                return False

            # Delete edges
            for edge_id in list(self._adj_out.get(node_key, set())):
                self.delete_edge(UUID(edge_id))
            for edge_id in list(self._adj_in.get(node_key, set())):
                self.delete_edge(UUID(edge_id))

            del self._nodes[node_key]
            self._adj_out.pop(node_key, None)
            self._adj_in.pop(node_key, None)
            return True

        # Check if node exists
        if self.db.get(self.NODE_PREFIX + node_key.encode()) is None:
            return False

        # Get and delete all edges
        neighbors = self.get_neighbors(node_id)
        for edge, _ in neighbors:
            self.delete_edge(edge.edge_id)

        # Delete node
        self.db.delete(self.NODE_PREFIX + node_key.encode())
        return True

    def add_edge(self, edge: Edge) -> Edge:
        """Add an edge to the graph."""
        edge_key = str(edge.edge_id)
        edge_data = json.dumps(edge.to_dict()).encode()

        if self._use_fallback:
            self._edges[edge_key] = edge

            source_key = str(edge.source_id)
            target_key = str(edge.target_id)

            if source_key not in self._adj_out:
                self._adj_out[source_key] = set()
            self._adj_out[source_key].add(edge_key)

            if target_key not in self._adj_in:
                self._adj_in[target_key] = set()
            self._adj_in[target_key].add(edge_key)
        else:
            batch = rocksdb.WriteBatch()

            # Store edge data
            batch.put(self.EDGE_PREFIX + edge_key.encode(), edge_data)

            # Store adjacency list entries
            out_key = f"adj:out:{edge.source_id}:{edge.edge_type.value}:{edge.target_id}:{edge.edge_id}"
            in_key = f"adj:in:{edge.target_id}:{edge.edge_type.value}:{edge.source_id}:{edge.edge_id}"

            batch.put(out_key.encode(), edge_key.encode())
            batch.put(in_key.encode(), edge_key.encode())

            self.db.write(batch)

        return edge

    def get_edge(self, edge_id: UUID) -> Edge | None:
        """Get an edge by ID."""
        edge_key = str(edge_id)

        if self._use_fallback:
            return self._edges.get(edge_key)

        edge_data = self.db.get(self.EDGE_PREFIX + edge_key.encode())
        if edge_data is None:
            return None

        return Edge.from_dict(json.loads(edge_data.decode()))

    def delete_edge(self, edge_id: UUID) -> bool:
        """Delete an edge."""
        edge_key = str(edge_id)

        if self._use_fallback:
            edge = self._edges.get(edge_key)
            if edge is None:
                return False

            source_key = str(edge.source_id)
            target_key = str(edge.target_id)

            self._adj_out.get(source_key, set()).discard(edge_key)
            self._adj_in.get(target_key, set()).discard(edge_key)
            del self._edges[edge_key]
            return True

        # Get edge to find adjacency keys
        edge = self.get_edge(edge_id)
        if edge is None:
            return False

        batch = rocksdb.WriteBatch()

        # Delete edge data
        batch.delete(self.EDGE_PREFIX + edge_key.encode())

        # Delete adjacency entries
        out_key = f"adj:out:{edge.source_id}:{edge.edge_type.value}:{edge.target_id}:{edge.edge_id}"
        in_key = f"adj:in:{edge.target_id}:{edge.edge_type.value}:{edge.source_id}:{edge.edge_id}"

        batch.delete(out_key.encode())
        batch.delete(in_key.encode())

        self.db.write(batch)
        return True

    def get_neighbors(
        self,
        node_id: UUID,
        edge_types: list[EdgeType] | None = None,
        direction: str = "both",
    ) -> list[tuple[Edge, Node]]:
        """Get neighboring nodes with their edges."""
        node_key = str(node_id)
        neighbors = []

        if self._use_fallback:
            edge_ids = set()
            if direction in ("outgoing", "both"):
                edge_ids.update(self._adj_out.get(node_key, set()))
            if direction in ("incoming", "both"):
                edge_ids.update(self._adj_in.get(node_key, set()))

            for edge_id in edge_ids:
                edge = self._edges.get(edge_id)
                if edge is None:
                    continue

                if edge_types and edge.edge_type not in edge_types:
                    continue

                # Get neighbor node
                neighbor_id = str(edge.target_id) if str(edge.source_id) == node_key else str(edge.source_id)
                neighbor = self._nodes.get(neighbor_id)

                if neighbor:
                    neighbors.append((edge, neighbor))
        else:
            # Scan adjacency lists
            prefixes = []
            if direction in ("outgoing", "both"):
                prefixes.append(f"adj:out:{node_id}:")
            if direction in ("incoming", "both"):
                prefixes.append(f"adj:in:{node_id}:")

            seen_edges = set()

            for prefix in prefixes:
                it = self.db.iteritems()
                it.seek(prefix.encode())

                for key, edge_id_bytes in it:
                    key_str = key.decode()
                    if not key_str.startswith(prefix):
                        break

                    edge_id = edge_id_bytes.decode()
                    if edge_id in seen_edges:
                        continue
                    seen_edges.add(edge_id)

                    edge = self.get_edge(UUID(edge_id))
                    if edge is None:
                        continue

                    if edge_types and edge.edge_type not in edge_types:
                        continue

                    # Get neighbor node
                    neighbor_id = edge.target_id if edge.source_id == node_id else edge.source_id
                    neighbor = self.get_node(neighbor_id)

                    if neighbor:
                        neighbors.append((edge, neighbor))

        return neighbors

    def find_path(
        self,
        start_id: UUID,
        end_id: UUID,
        max_depth: int = 5,
        edge_types: list[EdgeType] | None = None,
    ) -> PathResult | None:
        """Find shortest path using BFS."""
        if start_id == end_id:
            start_node = self.get_node(start_id)
            return PathResult(nodes=[start_node] if start_node else [], edges=[], length=0)

        # BFS
        from collections import deque

        visited = {start_id}
        queue: deque[tuple[UUID, list[tuple[Edge, Node]]]] = deque()
        queue.append((start_id, []))

        while queue:
            current_id, path = queue.popleft()

            if len(path) >= max_depth:
                continue

            for edge, neighbor in self.get_neighbors(current_id, edge_types):
                if neighbor.node_id in visited:
                    continue

                new_path = path + [(edge, neighbor)]

                if neighbor.node_id == end_id:
                    # Found path
                    start_node = self.get_node(start_id)
                    nodes = [start_node] if start_node else []
                    edges = []

                    for e, n in new_path:
                        nodes.append(n)
                        edges.append(e)

                    return PathResult(nodes=nodes, edges=edges, length=len(edges))

                visited.add(neighbor.node_id)
                queue.append((neighbor.node_id, new_path))

        return None

    def query(self, query: GraphQuery) -> list[Node]:
        """Execute a graph query."""
        results = []

        if self._use_fallback:
            for node in self._nodes.values():
                if query.node_type and node.node_type != query.node_type:
                    continue

                # Check property filters
                match = True
                for key, value in query.node_properties.items():
                    if node.properties.get(key) != value:
                        match = False
                        break

                if match:
                    results.append(node)

                    if len(results) >= query.offset + query.limit:
                        break

            return results[query.offset : query.offset + query.limit]

        # Scan all nodes
        it = self.db.iteritems()
        it.seek(self.NODE_PREFIX)
        count = 0
        skipped = 0

        for key, node_data in it:
            if not key.startswith(self.NODE_PREFIX):
                break

            node = Node.from_dict(json.loads(node_data.decode()))

            if query.node_type and node.node_type != query.node_type:
                continue

            # Check property filters
            match = True
            for prop_key, value in query.node_properties.items():
                if node.properties.get(prop_key) != value:
                    match = False
                    break

            if match:
                if skipped < query.offset:
                    skipped += 1
                    continue

                results.append(node)
                count += 1

                if count >= query.limit:
                    break

        return results

    def close(self) -> None:
        """Close the database."""
        if not self._use_fallback:
            del self.db
