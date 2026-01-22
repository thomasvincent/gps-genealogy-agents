"""Tests for Neo4j Graph Projection CQRS layer."""
from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from gps_agents.genealogy_crawler.graph import (
    AncestorResult,
    DescendantResult,
    Edge,
    EdgeType,
    FamilyUnit,
    FamilyUnitQuery,
    GraphProjection,
    KinshipQuery,
    KinshipResult,
    Node,
    NodeType,
    PedigreeQuery,
    PedigreeResult,
    PedigreeTraversal,
    PersonProjector,
    PersonSummary,
    ProjectionMetadata,
    ProjectionStatus,
    RelationshipType,
    RocksDBGraphStore,
    SyncEvent,
    TraversalDirection,
)


class TestPersonSummary:
    """Tests for PersonSummary model."""

    def test_create_person_summary(self):
        """Test basic creation."""
        person = PersonSummary(
            person_id=uuid4(),
            name="Archie Durham",
            birth_year=1927,
            death_year=2005,
            gender="male",
        )

        assert person.name == "Archie Durham"
        assert person.birth_year == 1927
        assert person.gender == "male"

    def test_to_dict(self):
        """Test serialization."""
        person_id = uuid4()
        person = PersonSummary(
            person_id=person_id,
            name="Ruth Durham",
            birth_year=1930,
        )

        data = person.to_dict()
        assert data["person_id"] == str(person_id)
        assert data["name"] == "Ruth Durham"
        assert data["birth_year"] == 1930
        assert data["death_year"] is None


class TestAncestorResult:
    """Tests for AncestorResult model."""

    def test_relationship_label_parent(self):
        """Test parent generation label."""
        ancestor = AncestorResult(
            person=PersonSummary(person_id=uuid4(), name="Father"),
            generation=1,
            lineage="paternal",
        )
        assert ancestor.relationship_label == "parent"

    def test_relationship_label_grandparent(self):
        """Test grandparent generation label."""
        ancestor = AncestorResult(
            person=PersonSummary(person_id=uuid4(), name="Grandfather"),
            generation=2,
            lineage="paternal",
        )
        assert ancestor.relationship_label == "grandparent"

    def test_relationship_label_great_grandparent(self):
        """Test great-grandparent generation label."""
        ancestor = AncestorResult(
            person=PersonSummary(person_id=uuid4(), name="Great-Grandfather"),
            generation=3,
            lineage="paternal",
        )
        assert ancestor.relationship_label == "great-grandparent"

    def test_relationship_label_multiple_greats(self):
        """Test multiple greats generation label."""
        ancestor = AncestorResult(
            person=PersonSummary(person_id=uuid4(), name="Ancestor"),
            generation=5,
            lineage="paternal",
        )
        assert ancestor.relationship_label == "great-great-great-grandparent"


class TestDescendantResult:
    """Tests for DescendantResult model."""

    def test_relationship_label_child(self):
        """Test child generation label."""
        descendant = DescendantResult(
            person=PersonSummary(person_id=uuid4(), name="Child"),
            generation=1,
        )
        assert descendant.relationship_label == "child"

    def test_relationship_label_grandchild(self):
        """Test grandchild generation label."""
        descendant = DescendantResult(
            person=PersonSummary(person_id=uuid4(), name="Grandchild"),
            generation=2,
        )
        assert descendant.relationship_label == "grandchild"


class TestKinshipResult:
    """Tests for KinshipResult model."""

    def test_degree_of_relationship(self):
        """Test degree calculation."""
        result = KinshipResult(
            person_a=PersonSummary(person_id=uuid4(), name="Person A"),
            person_b=PersonSummary(person_id=uuid4(), name="Person B"),
            relationship="first cousin",
            generations_to_common_ancestor_a=2,
            generations_to_common_ancestor_b=2,
        )

        assert result.degree_of_relationship == 4

    def test_coefficient_of_relationship_siblings(self):
        """Test coefficient for siblings."""
        result = KinshipResult(
            person_a=PersonSummary(person_id=uuid4(), name="Sibling A"),
            person_b=PersonSummary(person_id=uuid4(), name="Sibling B"),
            relationship="sibling",
            generations_to_common_ancestor_a=1,
            generations_to_common_ancestor_b=1,
        )

        # Full siblings share 50% DNA (through both parents, summed)
        # But for single common ancestor, r = 0.5^2 = 0.25
        assert result.coefficient_of_relationship == pytest.approx(0.25)

    def test_coefficient_of_relationship_first_cousins(self):
        """Test coefficient for first cousins."""
        result = KinshipResult(
            person_a=PersonSummary(person_id=uuid4(), name="Cousin A"),
            person_b=PersonSummary(person_id=uuid4(), name="Cousin B"),
            relationship="first cousin",
            generations_to_common_ancestor_a=2,
            generations_to_common_ancestor_b=2,
        )

        # First cousins: r = 0.5^4 = 0.0625
        assert result.coefficient_of_relationship == pytest.approx(0.0625)


class TestFamilyUnit:
    """Tests for FamilyUnit model."""

    def test_is_complete(self):
        """Test completeness check."""
        focal = PersonSummary(person_id=uuid4(), name="Focal Person")
        father = PersonSummary(person_id=uuid4(), name="Father")
        mother = PersonSummary(person_id=uuid4(), name="Mother")

        complete = FamilyUnit(
            focal_person=focal,
            father=father,
            mother=mother,
        )
        assert complete.is_complete is True

        incomplete = FamilyUnit(
            focal_person=focal,
            father=father,
            mother=None,
        )
        assert incomplete.is_complete is False

    def test_family_size(self):
        """Test family size calculation."""
        focal = PersonSummary(person_id=uuid4(), name="Focal")
        father = PersonSummary(person_id=uuid4(), name="Father")
        mother = PersonSummary(person_id=uuid4(), name="Mother")
        child1 = PersonSummary(person_id=uuid4(), name="Child 1")
        child2 = PersonSummary(person_id=uuid4(), name="Child 2")
        spouse = PersonSummary(person_id=uuid4(), name="Spouse")

        family = FamilyUnit(
            focal_person=focal,
            father=father,
            mother=mother,
            spouses=[spouse],
            children=[child1, child2],
        )

        # 1 focal + 2 parents + 1 spouse + 2 children = 6
        assert family.family_size == 6


class TestProjectionMetadata:
    """Tests for ProjectionMetadata model."""

    def test_is_current_synced(self):
        """Test is_current when synced."""
        metadata = ProjectionMetadata(
            status=ProjectionStatus.SYNCED,
            ledger_version=5,
            projection_version=5,
        )
        assert metadata.is_current is True

    def test_is_current_stale(self):
        """Test is_current when stale."""
        metadata = ProjectionMetadata(
            status=ProjectionStatus.SYNCED,
            ledger_version=6,
            projection_version=5,
        )
        assert metadata.is_current is False

    def test_is_current_syncing(self):
        """Test is_current when syncing."""
        metadata = ProjectionMetadata(
            status=ProjectionStatus.SYNCING,
            ledger_version=5,
            projection_version=5,
        )
        assert metadata.is_current is False


class TestPedigreeResult:
    """Tests for PedigreeResult model."""

    def test_create_pedigree_result(self):
        """Test creation with ancestors."""
        result = PedigreeResult(
            root_person_id=uuid4(),
            direction=TraversalDirection.ANCESTORS,
            generations_found=3,
            total_persons=7,
            ancestors=[
                {"person": {"name": "Parent"}, "generation": 1},
                {"person": {"name": "Grandparent"}, "generation": 2},
            ],
            query_time_ms=15.5,
        )

        assert result.generations_found == 3
        assert result.total_persons == 7
        assert len(result.ancestors) == 2


class TestGraphProjection:
    """Tests for GraphProjection CQRS sync."""

    @pytest.fixture
    def source_store(self):
        """Create source RocksDB store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RocksDBGraphStore(Path(tmpdir) / "source")
            yield store
            store.close()

    @pytest.fixture
    def target_store(self):
        """Create target RocksDB store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RocksDBGraphStore(Path(tmpdir) / "target")
            yield store
            store.close()

    def test_create_projection(self, source_store, target_store):
        """Test projection creation."""
        projection = GraphProjection(
            source_store=source_store,
            target_store=target_store,
        )

        assert projection.metadata.status == ProjectionStatus.STALE

    def test_queue_event(self, source_store, target_store):
        """Test event queuing."""
        projection = GraphProjection(
            source_store=source_store,
            target_store=target_store,
        )

        node = Node(
            node_id=uuid4(),
            node_type=NodeType.PERSON,
            properties={"name": "Test Person"},
        )
        event = projection.create_node_added_event(node)
        projection.queue_event(event)

        assert projection.metadata.status == ProjectionStatus.STALE
        assert projection.metadata.ledger_version == 1

    @pytest.mark.asyncio
    async def test_full_sync(self, source_store, target_store):
        """Test full projection sync."""
        # Add data to source
        person1 = Node(
            node_id=uuid4(),
            node_type=NodeType.PERSON,
            properties={"name": "Person 1"},
        )
        person2 = Node(
            node_id=uuid4(),
            node_type=NodeType.PERSON,
            properties={"name": "Person 2"},
        )
        source_store.add_node(person1)
        source_store.add_node(person2)

        edge = Edge(
            edge_id=uuid4(),
            edge_type=EdgeType.PARENT_OF,
            source_id=person1.node_id,
            target_id=person2.node_id,
        )
        source_store.add_edge(edge)

        # Sync to target
        projection = GraphProjection(
            source_store=source_store,
            target_store=target_store,
        )

        metadata = await projection.sync(full_rebuild=True)

        assert metadata.status == ProjectionStatus.SYNCED
        assert metadata.total_nodes == 2
        assert metadata.total_edges == 1

        # Verify target has data
        assert target_store.get_node(person1.node_id) is not None
        assert target_store.get_node(person2.node_id) is not None


class TestPersonProjector:
    """Tests for PersonProjector."""

    @pytest.fixture
    def projection(self):
        """Create a projection for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = RocksDBGraphStore(Path(tmpdir) / "source")
            target = RocksDBGraphStore(Path(tmpdir) / "target")
            proj = GraphProjection(source, target)
            yield proj
            source.close()
            target.close()

    def test_project_person(self, projection):
        """Test projecting a person node."""
        projector = PersonProjector(projection)

        person_id = uuid4()
        node = projector.project_person(
            person_id=person_id,
            name="Archie Durham",
            birth_year=1927,
            death_year=2005,
            gender="male",
        )

        assert node.node_id == person_id
        assert node.node_type == NodeType.PERSON
        assert node.properties["name"] == "Archie Durham"
        assert node.properties["birth_year"] == 1927

    def test_project_parent_child(self, projection):
        """Test projecting parent-child relationship."""
        projector = PersonProjector(projection)

        parent_id = uuid4()
        child_id = uuid4()

        edge = projector.project_parent_child(
            parent_id=parent_id,
            child_id=child_id,
            parent_role="father",
            confidence=0.95,
        )

        assert edge.edge_type == EdgeType.PARENT_OF
        assert edge.source_id == parent_id
        assert edge.target_id == child_id
        assert edge.confidence == 0.95

    def test_project_spouse(self, projection):
        """Test projecting spouse relationship."""
        projector = PersonProjector(projection)

        person_a = uuid4()
        person_b = uuid4()

        edge = projector.project_spouse(
            person_a_id=person_a,
            person_b_id=person_b,
            marriage_year=1950,
        )

        assert edge.edge_type == EdgeType.SPOUSE_OF
        assert edge.properties["marriage_year"] == 1950


class TestPedigreeTraversal:
    """Tests for PedigreeTraversal queries."""

    @pytest.fixture
    def family_graph(self):
        """Create a family graph for testing.

        Creates a 3-generation family:
        - Grandfather + Grandmother -> Father
        - Father + Mother -> Child
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RocksDBGraphStore(Path(tmpdir) / "graph")

            # Create nodes
            grandfather = Node(
                node_id=uuid4(),
                node_type=NodeType.PERSON,
                properties={"name": "Grandfather", "gender": "male", "birth_year": 1900},
            )
            grandmother = Node(
                node_id=uuid4(),
                node_type=NodeType.PERSON,
                properties={"name": "Grandmother", "gender": "female", "birth_year": 1905},
            )
            father = Node(
                node_id=uuid4(),
                node_type=NodeType.PERSON,
                properties={"name": "Father", "gender": "male", "birth_year": 1930},
            )
            mother = Node(
                node_id=uuid4(),
                node_type=NodeType.PERSON,
                properties={"name": "Mother", "gender": "female", "birth_year": 1935},
            )
            child = Node(
                node_id=uuid4(),
                node_type=NodeType.PERSON,
                properties={"name": "Child", "gender": "male", "birth_year": 1960},
            )

            for node in [grandfather, grandmother, father, mother, child]:
                store.add_node(node)

            # Create parent-child edges (CHILD_OF goes from child to parent)
            edges = [
                Edge(
                    edge_type=EdgeType.CHILD_OF,
                    source_id=father.node_id,
                    target_id=grandfather.node_id,
                    properties={"parent_role": "father"},
                ),
                Edge(
                    edge_type=EdgeType.CHILD_OF,
                    source_id=father.node_id,
                    target_id=grandmother.node_id,
                    properties={"parent_role": "mother"},
                ),
                Edge(
                    edge_type=EdgeType.CHILD_OF,
                    source_id=child.node_id,
                    target_id=father.node_id,
                    properties={"parent_role": "father"},
                ),
                Edge(
                    edge_type=EdgeType.CHILD_OF,
                    source_id=child.node_id,
                    target_id=mother.node_id,
                    properties={"parent_role": "mother"},
                ),
                # Also add PARENT_OF edges for descendant traversal
                Edge(
                    edge_type=EdgeType.PARENT_OF,
                    source_id=grandfather.node_id,
                    target_id=father.node_id,
                ),
                Edge(
                    edge_type=EdgeType.PARENT_OF,
                    source_id=grandmother.node_id,
                    target_id=father.node_id,
                ),
                Edge(
                    edge_type=EdgeType.PARENT_OF,
                    source_id=father.node_id,
                    target_id=child.node_id,
                ),
                Edge(
                    edge_type=EdgeType.PARENT_OF,
                    source_id=mother.node_id,
                    target_id=child.node_id,
                ),
                # Spouse edge
                Edge(
                    edge_type=EdgeType.SPOUSE_OF,
                    source_id=father.node_id,
                    target_id=mother.node_id,
                ),
            ]

            for edge in edges:
                store.add_edge(edge)

            yield store, {
                "grandfather": grandfather,
                "grandmother": grandmother,
                "father": father,
                "mother": mother,
                "child": child,
            }

            store.close()

    @pytest.mark.asyncio
    async def test_get_ancestors(self, family_graph):
        """Test ancestor traversal."""
        store, people = family_graph
        traversal = PedigreeTraversal(store)

        result = await traversal.get_ancestors(
            person_id=people["child"].node_id,
            max_generations=3,
        )

        assert result.direction == TraversalDirection.ANCESTORS
        assert result.total_persons >= 2  # At least father and mother

        # Check we have parents
        names = [a["person"]["name"] for a in result.ancestors]
        assert "Father" in names
        assert "Mother" in names

    @pytest.mark.asyncio
    async def test_get_descendants(self, family_graph):
        """Test descendant traversal."""
        store, people = family_graph
        traversal = PedigreeTraversal(store)

        result = await traversal.get_descendants(
            person_id=people["grandfather"].node_id,
            max_generations=3,
        )

        assert result.direction == TraversalDirection.DESCENDANTS
        assert result.total_persons >= 1  # At least father

        names = [d["person"]["name"] for d in result.descendants]
        assert "Father" in names

    @pytest.mark.asyncio
    async def test_find_kinship_self(self, family_graph):
        """Test kinship computation for same person."""
        store, people = family_graph
        traversal = PedigreeTraversal(store)

        query = KinshipQuery(
            person_a_id=people["child"].node_id,
            person_b_id=people["child"].node_id,
            max_generations=5,
        )

        result = await traversal.find_kinship(query)

        assert result is not None
        assert result.relationship == "self"
        assert result.path_length == 0

    @pytest.mark.asyncio
    async def test_get_family_unit(self, family_graph):
        """Test family unit reconstruction."""
        store, people = family_graph
        traversal = PedigreeTraversal(store)

        query = FamilyUnitQuery(
            person_id=people["child"].node_id,
            include_parents=True,
            include_spouse=True,
        )

        family = await traversal.get_family_unit(query)

        assert family is not None
        assert family.focal_person.name == "Child"
        assert family.father is not None
        assert family.father.name == "Father"
        assert family.mother is not None
        assert family.mother.name == "Mother"


class TestRelationshipType:
    """Tests for RelationshipType enum."""

    def test_basic_relationships(self):
        """Test basic relationship values."""
        assert RelationshipType.FATHER.value == "father"
        assert RelationshipType.MOTHER.value == "mother"
        assert RelationshipType.SPOUSE.value == "spouse"
        assert RelationshipType.SIBLING.value == "sibling"

    def test_extended_relationships(self):
        """Test extended relationship values."""
        assert RelationshipType.GRANDFATHER.value == "grandfather"
        assert RelationshipType.COUSIN.value == "cousin"
        assert RelationshipType.UNCLE.value == "uncle"


class TestTraversalDirection:
    """Tests for TraversalDirection enum."""

    def test_direction_values(self):
        """Test direction values."""
        assert TraversalDirection.ANCESTORS.value == "ancestors"
        assert TraversalDirection.DESCENDANTS.value == "descendants"
        assert TraversalDirection.BOTH.value == "both"
