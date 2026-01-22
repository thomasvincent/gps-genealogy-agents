"""Pedigree traversal queries for genealogical graph.

Provides specialized queries for:
- Ancestor traversal (parents, grandparents, etc.)
- Descendant traversal (children, grandchildren, etc.)
- Kinship computation (how are two people related?)
- Family unit reconstruction

Optimized for Neo4j Cypher queries but works with any GraphStore.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import TYPE_CHECKING
from uuid import UUID

from .graph_store import Edge, EdgeType, GraphStore, Node
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
    RelationshipType,
    TraversalDirection,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PedigreeTraversal:
    """Genealogical graph traversal engine.

    Provides optimized queries for ancestor/descendant traversal,
    kinship computation, and family unit reconstruction.

    Example:
        >>> traversal = PedigreeTraversal(graph_store)
        >>> result = await traversal.get_ancestors(
        ...     person_id=uuid,
        ...     max_generations=4,
        ... )
        >>> for ancestor in result.ancestors:
        ...     print(f"{ancestor['generation']}: {ancestor['person']['name']}")
    """

    def __init__(self, graph_store: GraphStore) -> None:
        """Initialize traversal engine.

        Args:
            graph_store: Graph store to query (Neo4j or RocksDB)
        """
        self.store = graph_store

    async def get_ancestors(
        self,
        person_id: UUID,
        max_generations: int = 4,
        min_confidence: float = 0.0,
    ) -> PedigreeResult:
        """Get all ancestors up to specified generation.

        Uses BFS traversal following PARENT_OF edges in reverse.

        Args:
            person_id: Root person to start from
            max_generations: Maximum generations to traverse (1=parents, 2=grandparents)
            min_confidence: Minimum edge confidence to include

        Returns:
            PedigreeResult with ancestors organized by generation
        """
        start_time = time.time()
        ancestors: list[dict] = []
        visited: set[UUID] = {person_id}

        # BFS traversal
        queue: deque[tuple[UUID, int, str, list[RelationshipType]]] = deque()

        # Get parents of root person
        parents = self.store.get_neighbors(
            person_id,
            edge_types=[EdgeType.CHILD_OF],
            direction="outgoing",
        )

        for edge, parent_node in parents:
            if edge.confidence >= min_confidence:
                lineage = self._determine_lineage(parent_node)
                queue.append((parent_node.node_id, 1, lineage, [self._get_parent_type(parent_node)]))
                visited.add(parent_node.node_id)

        while queue:
            current_id, generation, lineage, path = queue.popleft()

            if generation > max_generations:
                continue

            node = self.store.get_node(current_id)
            if node is None:
                continue

            person = self._node_to_person_summary(node)
            ancestor = AncestorResult(
                person=person,
                generation=generation,
                lineage=lineage,
                relationship_path=path,
                confidence=1.0,
            )
            ancestors.append({
                "person": person.to_dict(),
                "generation": generation,
                "lineage": lineage,
                "relationship_label": ancestor.relationship_label,
                "confidence": ancestor.confidence,
            })

            # Continue to next generation if not at limit
            if generation < max_generations:
                parent_neighbors = self.store.get_neighbors(
                    current_id,
                    edge_types=[EdgeType.CHILD_OF],
                    direction="outgoing",
                )

                for edge, parent_node in parent_neighbors:
                    if parent_node.node_id not in visited and edge.confidence >= min_confidence:
                        new_lineage = lineage  # Preserve original lineage
                        new_path = path + [self._get_parent_type(parent_node)]
                        queue.append((parent_node.node_id, generation + 1, new_lineage, new_path))
                        visited.add(parent_node.node_id)

        query_time = (time.time() - start_time) * 1000

        return PedigreeResult(
            root_person_id=person_id,
            direction=TraversalDirection.ANCESTORS,
            generations_found=max(a["generation"] for a in ancestors) if ancestors else 0,
            total_persons=len(ancestors),
            ancestors=ancestors,
            query_time_ms=query_time,
        )

    async def get_descendants(
        self,
        person_id: UUID,
        max_generations: int = 4,
        min_confidence: float = 0.0,
    ) -> PedigreeResult:
        """Get all descendants down to specified generation.

        Uses BFS traversal following PARENT_OF edges forward.

        Args:
            person_id: Root person to start from
            max_generations: Maximum generations to traverse (1=children, 2=grandchildren)
            min_confidence: Minimum edge confidence to include

        Returns:
            PedigreeResult with descendants organized by generation
        """
        start_time = time.time()
        descendants: list[dict] = []
        visited: set[UUID] = {person_id}

        # BFS traversal
        queue: deque[tuple[UUID, int, list[RelationshipType]]] = deque()

        # Get children of root person
        children = self.store.get_neighbors(
            person_id,
            edge_types=[EdgeType.PARENT_OF],
            direction="outgoing",
        )

        for edge, child_node in children:
            if edge.confidence >= min_confidence:
                queue.append((child_node.node_id, 1, [self._get_child_type(child_node)]))
                visited.add(child_node.node_id)

        while queue:
            current_id, generation, path = queue.popleft()

            if generation > max_generations:
                continue

            node = self.store.get_node(current_id)
            if node is None:
                continue

            person = self._node_to_person_summary(node)
            descendant = DescendantResult(
                person=person,
                generation=generation,
                relationship_path=path,
                confidence=1.0,
            )
            descendants.append({
                "person": person.to_dict(),
                "generation": generation,
                "relationship_label": descendant.relationship_label,
                "confidence": descendant.confidence,
            })

            # Continue to next generation if not at limit
            if generation < max_generations:
                child_neighbors = self.store.get_neighbors(
                    current_id,
                    edge_types=[EdgeType.PARENT_OF],
                    direction="outgoing",
                )

                for edge, child_node in child_neighbors:
                    if child_node.node_id not in visited and edge.confidence >= min_confidence:
                        new_path = path + [self._get_child_type(child_node)]
                        queue.append((child_node.node_id, generation + 1, new_path))
                        visited.add(child_node.node_id)

        query_time = (time.time() - start_time) * 1000

        return PedigreeResult(
            root_person_id=person_id,
            direction=TraversalDirection.DESCENDANTS,
            generations_found=max(d["generation"] for d in descendants) if descendants else 0,
            total_persons=len(descendants),
            descendants=descendants,
            query_time_ms=query_time,
        )

    async def find_kinship(
        self,
        query: KinshipQuery,
    ) -> KinshipResult | None:
        """Find relationship between two people.

        Uses bidirectional BFS to find common ancestors, then
        computes the genealogical relationship.

        Args:
            query: Kinship query parameters

        Returns:
            KinshipResult if related, None if no relationship found
        """
        person_a_id = query.person_a_id
        person_b_id = query.person_b_id

        if person_a_id == person_b_id:
            node = self.store.get_node(person_a_id)
            if node:
                person = self._node_to_person_summary(node)
                return KinshipResult(
                    person_a=person,
                    person_b=person,
                    relationship="self",
                    path_length=0,
                )
            return None

        # Get ancestors of both persons
        ancestors_a = await self._get_ancestor_set(person_a_id, query.max_generations)
        ancestors_b = await self._get_ancestor_set(person_b_id, query.max_generations)

        # Find common ancestors
        common_ancestor_ids = ancestors_a.keys() & ancestors_b.keys()

        if not common_ancestor_ids:
            return None

        # Find closest common ancestor
        min_total_distance = float("inf")
        closest_ancestor_id = None

        for ancestor_id in common_ancestor_ids:
            gen_a = ancestors_a[ancestor_id]
            gen_b = ancestors_b[ancestor_id]
            total = gen_a + gen_b

            if total < min_total_distance:
                min_total_distance = total
                closest_ancestor_id = ancestor_id

        if closest_ancestor_id is None:
            return None

        gen_a = ancestors_a[closest_ancestor_id]
        gen_b = ancestors_b[closest_ancestor_id]

        # Get person summaries
        node_a = self.store.get_node(person_a_id)
        node_b = self.store.get_node(person_b_id)
        ancestor_node = self.store.get_node(closest_ancestor_id)

        if not (node_a and node_b and ancestor_node):
            return None

        person_a = self._node_to_person_summary(node_a)
        person_b = self._node_to_person_summary(node_b)
        common_ancestor = self._node_to_person_summary(ancestor_node)

        # Compute relationship label
        relationship = self._compute_relationship_label(gen_a, gen_b)

        return KinshipResult(
            person_a=person_a,
            person_b=person_b,
            relationship=relationship,
            common_ancestors=[common_ancestor],
            path_length=gen_a + gen_b,
            generations_to_common_ancestor_a=gen_a,
            generations_to_common_ancestor_b=gen_b,
        )

    async def get_family_unit(
        self,
        query: FamilyUnitQuery,
    ) -> FamilyUnit | None:
        """Reconstruct a family unit centered on a person.

        Args:
            query: Family unit query parameters

        Returns:
            FamilyUnit with parents, spouse, children, siblings
        """
        focal_node = self.store.get_node(query.person_id)
        if focal_node is None:
            return None

        focal_person = self._node_to_person_summary(focal_node)
        father: PersonSummary | None = None
        mother: PersonSummary | None = None
        spouses: list[PersonSummary] = []
        children: list[PersonSummary] = []
        siblings: list[PersonSummary] = []

        # Get parents
        if query.include_parents:
            parents = self.store.get_neighbors(
                query.person_id,
                edge_types=[EdgeType.CHILD_OF],
                direction="outgoing",
            )

            for edge, parent_node in parents:
                parent = self._node_to_person_summary(parent_node)
                gender = parent_node.properties.get("gender", "").lower()

                if gender == "male" or edge.properties.get("parent_role") == "father":
                    father = parent
                elif gender == "female" or edge.properties.get("parent_role") == "mother":
                    mother = parent

        # Get spouse(s)
        if query.include_spouse:
            spouse_neighbors = self.store.get_neighbors(
                query.person_id,
                edge_types=[EdgeType.SPOUSE_OF],
                direction="both",
            )

            for _, spouse_node in spouse_neighbors:
                spouses.append(self._node_to_person_summary(spouse_node))

        # Get children
        if query.include_children:
            child_neighbors = self.store.get_neighbors(
                query.person_id,
                edge_types=[EdgeType.PARENT_OF],
                direction="outgoing",
            )

            for _, child_node in child_neighbors:
                children.append(self._node_to_person_summary(child_node))

        # Get siblings (through shared parents)
        if query.include_siblings and (father or mother):
            sibling_ids: set[UUID] = set()

            for parent in [father, mother]:
                if parent:
                    parent_children = self.store.get_neighbors(
                        parent.person_id,
                        edge_types=[EdgeType.PARENT_OF],
                        direction="outgoing",
                    )

                    for _, sibling_node in parent_children:
                        if sibling_node.node_id != query.person_id:
                            sibling_ids.add(sibling_node.node_id)

            for sibling_id in sibling_ids:
                sibling_node = self.store.get_node(sibling_id)
                if sibling_node:
                    siblings.append(self._node_to_person_summary(sibling_node))

        return FamilyUnit(
            focal_person=focal_person,
            father=father,
            mother=mother,
            spouses=spouses,
            children=children,
            siblings=siblings,
        )

    async def _get_ancestor_set(
        self,
        person_id: UUID,
        max_generations: int,
    ) -> dict[UUID, int]:
        """Get all ancestors with their generation distance.

        Returns:
            Dict mapping ancestor_id -> generation distance
        """
        ancestors: dict[UUID, int] = {}
        visited: set[UUID] = {person_id}
        queue: deque[tuple[UUID, int]] = deque()

        # Start with parents
        parents = self.store.get_neighbors(
            person_id,
            edge_types=[EdgeType.CHILD_OF],
            direction="outgoing",
        )

        for _, parent_node in parents:
            queue.append((parent_node.node_id, 1))
            visited.add(parent_node.node_id)

        while queue:
            current_id, generation = queue.popleft()

            if generation > max_generations:
                continue

            ancestors[current_id] = generation

            # Get parents of current
            parent_neighbors = self.store.get_neighbors(
                current_id,
                edge_types=[EdgeType.CHILD_OF],
                direction="outgoing",
            )

            for _, parent_node in parent_neighbors:
                if parent_node.node_id not in visited:
                    queue.append((parent_node.node_id, generation + 1))
                    visited.add(parent_node.node_id)

        return ancestors

    def _node_to_person_summary(self, node: Node) -> PersonSummary:
        """Convert graph node to person summary."""
        return PersonSummary(
            person_id=node.node_id,
            name=node.properties.get("name", "Unknown"),
            birth_year=node.properties.get("birth_year"),
            death_year=node.properties.get("death_year"),
            gender=node.properties.get("gender"),
        )

    def _determine_lineage(self, parent_node: Node) -> str:
        """Determine if parent is paternal or maternal."""
        gender = parent_node.properties.get("gender", "").lower()
        if gender == "male":
            return "paternal"
        elif gender == "female":
            return "maternal"
        return "unknown"

    def _get_parent_type(self, parent_node: Node) -> RelationshipType:
        """Get relationship type for parent."""
        gender = parent_node.properties.get("gender", "").lower()
        if gender == "male":
            return RelationshipType.FATHER
        elif gender == "female":
            return RelationshipType.MOTHER
        return RelationshipType.PARENT

    def _get_child_type(self, child_node: Node) -> RelationshipType:
        """Get relationship type for child."""
        gender = child_node.properties.get("gender", "").lower()
        if gender == "male":
            return RelationshipType.SON
        elif gender == "female":
            return RelationshipType.DAUGHTER
        return RelationshipType.CHILD

    def _compute_relationship_label(
        self,
        generations_a: int,
        generations_b: int,
    ) -> str:
        """Compute relationship label from generation distances.

        Uses standard genealogical terminology.
        """
        if generations_a == 0 and generations_b == 0:
            return "self"
        elif generations_a == 0:
            return self._descendant_label(generations_b)
        elif generations_b == 0:
            return self._ancestor_label(generations_a)
        elif generations_a == 1 and generations_b == 1:
            return "sibling"
        elif generations_a == 1:
            # Person A is parent's sibling (uncle/aunt) to person B
            return f"{'great-' * (generations_b - 2)}{'uncle/aunt' if generations_b > 1 else 'uncle/aunt'}"
        elif generations_b == 1:
            # Person B is parent's sibling (uncle/aunt) to person A
            return f"{'great-' * (generations_a - 2)}{'nephew/niece' if generations_a > 1 else 'nephew/niece'}"
        else:
            # Cousins
            cousin_degree = min(generations_a, generations_b) - 1
            removal = abs(generations_a - generations_b)

            if cousin_degree == 1:
                base = "first cousin"
            elif cousin_degree == 2:
                base = "second cousin"
            elif cousin_degree == 3:
                base = "third cousin"
            else:
                base = f"{cousin_degree}th cousin"

            if removal == 0:
                return base
            elif removal == 1:
                return f"{base} once removed"
            elif removal == 2:
                return f"{base} twice removed"
            else:
                return f"{base} {removal} times removed"

    def _ancestor_label(self, generations: int) -> str:
        """Get label for direct ancestor."""
        if generations == 1:
            return "parent"
        elif generations == 2:
            return "grandparent"
        else:
            return f"{'great-' * (generations - 2)}grandparent"

    def _descendant_label(self, generations: int) -> str:
        """Get label for direct descendant."""
        if generations == 1:
            return "child"
        elif generations == 2:
            return "grandchild"
        else:
            return f"{'great-' * (generations - 2)}grandchild"


class Neo4jPedigreeTraversal(PedigreeTraversal):
    """Neo4j-optimized pedigree traversal using Cypher.

    Provides native Cypher queries for better performance
    on large genealogical databases.
    """

    def __init__(self, graph_store: GraphStore) -> None:
        super().__init__(graph_store)

        # Check if store is Neo4j
        from .graph_store import Neo4jGraphStore
        if not isinstance(graph_store, Neo4jGraphStore):
            logger.warning(
                "Neo4jPedigreeTraversal initialized with non-Neo4j store. "
                "Falling back to generic traversal."
            )
            self._use_cypher = False
        else:
            self._use_cypher = True
            self._driver = graph_store.driver
            self._database = graph_store.database

    async def get_ancestors_cypher(
        self,
        person_id: UUID,
        max_generations: int = 4,
    ) -> PedigreeResult:
        """Get ancestors using native Cypher query.

        Uses variable-length path matching for efficiency.
        """
        if not self._use_cypher:
            return await self.get_ancestors(person_id, max_generations)

        start_time = time.time()

        with self._driver.session(database=self._database) as session:
            result = session.run(
                """
                MATCH path = (person {node_id: $person_id})-[:CHILD_OF*1..]->(ancestor)
                WHERE length(path) <= $max_gen
                RETURN ancestor, length(path) as generation
                ORDER BY generation
                """,
                person_id=str(person_id),
                max_gen=max_generations,
            )

            ancestors = []
            max_gen_found = 0

            for record in result:
                neo_node = record["ancestor"]
                generation = record["generation"]
                max_gen_found = max(max_gen_found, generation)

                props = dict(neo_node)
                person = PersonSummary(
                    person_id=UUID(props.get("node_id", str(uuid4()))),
                    name=props.get("name", "Unknown"),
                    birth_year=props.get("birth_year"),
                    death_year=props.get("death_year"),
                    gender=props.get("gender"),
                )

                ancestors.append({
                    "person": person.to_dict(),
                    "generation": generation,
                    "lineage": self._determine_lineage_from_props(props),
                    "relationship_label": self._ancestor_label(generation),
                    "confidence": 1.0,
                })

        query_time = (time.time() - start_time) * 1000

        return PedigreeResult(
            root_person_id=person_id,
            direction=TraversalDirection.ANCESTORS,
            generations_found=max_gen_found,
            total_persons=len(ancestors),
            ancestors=ancestors,
            query_time_ms=query_time,
        )

    async def find_kinship_cypher(
        self,
        query: KinshipQuery,
    ) -> KinshipResult | None:
        """Find kinship using Cypher shortest path.

        Uses Neo4j's shortestPath algorithm for efficiency.
        """
        if not self._use_cypher:
            return await self.find_kinship(query)

        with self._driver.session(database=self._database) as session:
            result = session.run(
                """
                MATCH (a {node_id: $person_a}), (b {node_id: $person_b})
                MATCH path = shortestPath((a)-[:CHILD_OF|PARENT_OF*..]->(b))
                WHERE length(path) <= $max_gen * 2
                RETURN path, length(path) as path_length
                LIMIT 1
                """,
                person_a=str(query.person_a_id),
                person_b=str(query.person_b_id),
                max_gen=query.max_generations,
            )

            record = result.single()
            if record is None:
                return None

            # Would need additional processing to extract
            # common ancestor and compute relationship
            # For now, fall back to generic implementation
            return await self.find_kinship(query)

    def _determine_lineage_from_props(self, props: dict) -> str:
        """Determine lineage from node properties."""
        gender = props.get("gender", "").lower()
        if gender == "male":
            return "paternal"
        elif gender == "female":
            return "maternal"
        return "unknown"
