"""Semantic Kernel plugin for semantic memory (ChromaDB)."""

import json
from typing import Annotated

from semantic_kernel.functions import kernel_function
from uuid_utils import uuid7

try:
    import chromadb
    from chromadb.config import Settings

    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False


class MemoryPlugin:
    """Plugin for semantic memory using ChromaDB.

    Provides semantic search capabilities for:
    - Facts: Find similar/related facts
    - Sources: Deduplicate sources
    - Research context: Track research patterns
    """

    FACTS_COLLECTION = "facts"
    SOURCES_COLLECTION = "sources"
    RESEARCH_COLLECTION = "research_context"

    def __init__(self, persist_directory: str) -> None:
        self.persist_directory = persist_directory

        if CHROMA_AVAILABLE:
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(anonymized_telemetry=False),
            )
            self._ensure_collections()
        else:
            self.client = None

    def _ensure_collections(self) -> None:
        """Create collections if they don't exist."""
        if self.client is None:
            return

        self.client.get_or_create_collection(
            name=self.FACTS_COLLECTION,
            metadata={"description": "Genealogical facts for semantic search"},
        )
        self.client.get_or_create_collection(
            name=self.SOURCES_COLLECTION,
            metadata={"description": "Source citations for deduplication"},
        )
        self.client.get_or_create_collection(
            name=self.RESEARCH_COLLECTION,
            metadata={"description": "Research context and patterns"},
        )

    @kernel_function(
        name="store_fact",
        description="Store a fact in semantic memory for similarity search.",
    )
    def store_fact(
        self,
        fact_id: Annotated[str, "UUID of the fact"],
        statement: Annotated[str, "The fact statement text"],
        metadata_json: Annotated[str, "JSON metadata (status, confidence, etc.)"] = "{}",
    ) -> Annotated[str, "Storage confirmation"]:
        """Store a fact for semantic search."""
        if self.client is None:
            return json.dumps({"error": "ChromaDB not available"})

        collection = self.client.get_collection(self.FACTS_COLLECTION)
        metadata = json.loads(metadata_json)
        metadata["fact_id"] = fact_id

        collection.upsert(
            ids=[fact_id],
            documents=[statement],
            metadatas=[metadata],
        )

        return json.dumps({"success": True, "fact_id": fact_id})

    @kernel_function(
        name="search_similar_facts",
        description="Find facts semantically similar to a query.",
    )
    def search_similar_facts(
        self,
        query: Annotated[str, "Search query text"],
        n_results: Annotated[int, "Number of results to return"] = 10,
        status_filter: Annotated[str | None, "Filter by status (ACCEPTED, etc.)"] = None,
    ) -> Annotated[str, "JSON array of similar facts"]:
        """Search for semantically similar facts."""
        if self.client is None:
            return json.dumps({"error": "ChromaDB not available"})

        collection = self.client.get_collection(self.FACTS_COLLECTION)

        where_filter = None
        if status_filter:
            where_filter = {"status": status_filter.upper()}

        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter,
        )

        similar = []
        if results["ids"] and results["ids"][0]:
            for i, fact_id in enumerate(results["ids"][0]):
                similar.append({
                    "fact_id": fact_id,
                    "statement": results["documents"][0][i] if results["documents"] else None,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })

        return json.dumps(similar)

    @kernel_function(
        name="store_source",
        description="Store a source citation for deduplication checks.",
    )
    def store_source(
        self,
        source_id: Annotated[str, "Unique source identifier"],
        citation_text: Annotated[str, "Full citation text"],
        metadata_json: Annotated[str, "JSON metadata"] = "{}",
    ) -> Annotated[str, "Storage confirmation"]:
        """Store source for deduplication."""
        if self.client is None:
            return json.dumps({"error": "ChromaDB not available"})

        collection = self.client.get_collection(self.SOURCES_COLLECTION)
        metadata = json.loads(metadata_json)
        metadata["source_id"] = source_id

        collection.upsert(
            ids=[source_id],
            documents=[citation_text],
            metadatas=[metadata],
        )

        return json.dumps({"success": True, "source_id": source_id})

    @kernel_function(
        name="find_duplicate_sources",
        description="Find potentially duplicate sources.",
    )
    def find_duplicate_sources(
        self,
        citation_text: Annotated[str, "Citation text to check for duplicates"],
        similarity_threshold: Annotated[float, "Similarity threshold (0-1)"] = 0.9,
    ) -> Annotated[str, "JSON array of potential duplicates"]:
        """Find sources that might be duplicates."""
        if self.client is None:
            return json.dumps({"error": "ChromaDB not available"})

        collection = self.client.get_collection(self.SOURCES_COLLECTION)

        results = collection.query(
            query_texts=[citation_text],
            n_results=5,
        )

        duplicates = []
        if results["ids"] and results["ids"][0]:
            for i, source_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results["distances"] else 1.0
                similarity = 1.0 - distance

                if similarity >= similarity_threshold:
                    duplicates.append({
                        "source_id": source_id,
                        "citation": results["documents"][0][i] if results["documents"] else None,
                        "similarity": similarity,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    })

        return json.dumps(duplicates)

    @kernel_function(
        name="store_research_context",
        description="Store research context for learning patterns.",
    )
    def store_research_context(
        self,
        context_text: Annotated[str, "Research context description"],
        context_type: Annotated[str, "Type: search_strategy, resolution, insight"],
        related_facts: Annotated[str, "JSON array of related fact IDs"] = "[]",
    ) -> Annotated[str, "Storage confirmation"]:
        """Store research context for pattern learning."""
        if self.client is None:
            return json.dumps({"error": "ChromaDB not available"})

        collection = self.client.get_collection(self.RESEARCH_COLLECTION)
        context_id = str(uuid7())

        collection.add(
            ids=[context_id],
            documents=[context_text],
            metadatas=[{
                "context_type": context_type,
                "related_facts": related_facts,
            }],
        )

        return json.dumps({"success": True, "context_id": context_id})

    @kernel_function(
        name="get_research_insights",
        description="Get relevant research insights for a query.",
    )
    def get_research_insights(
        self,
        query: Annotated[str, "Research query or context"],
        context_type: Annotated[str | None, "Filter by context type"] = None,
        n_results: Annotated[int, "Number of results"] = 5,
    ) -> Annotated[str, "JSON array of relevant insights"]:
        """Get research insights relevant to a query."""
        if self.client is None:
            return json.dumps({"error": "ChromaDB not available"})

        collection = self.client.get_collection(self.RESEARCH_COLLECTION)

        where_filter = None
        if context_type:
            where_filter = {"context_type": context_type}

        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter,
        )

        insights = []
        if results["ids"] and results["ids"][0]:
            for i, context_id in enumerate(results["ids"][0]):
                insights.append({
                    "context_id": context_id,
                    "context": results["documents"][0][i] if results["documents"] else None,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                })

        return json.dumps(insights)

    @kernel_function(
        name="get_memory_stats",
        description="Get statistics about stored memories.",
    )
    def get_memory_stats(self) -> Annotated[str, "JSON with memory statistics"]:
        """Get memory statistics."""
        if self.client is None:
            return json.dumps({"error": "ChromaDB not available", "available": False})

        facts = self.client.get_collection(self.FACTS_COLLECTION)
        sources = self.client.get_collection(self.SOURCES_COLLECTION)
        research = self.client.get_collection(self.RESEARCH_COLLECTION)

        return json.dumps({
            "available": True,
            "collections": {
                "facts": facts.count(),
                "sources": sources.count(),
                "research_context": research.count(),
            },
            "persist_directory": self.persist_directory,
        })

    @kernel_function(
        name="clear_collection",
        description="Clear all items from a specific collection.",
    )
    def clear_collection(
        self,
        collection_name: Annotated[str, "Collection to clear: facts, sources, or research_context"],
    ) -> Annotated[str, "Confirmation"]:
        """Clear a collection."""
        if self.client is None:
            return json.dumps({"error": "ChromaDB not available"})

        valid_names = {
            "facts": self.FACTS_COLLECTION,
            "sources": self.SOURCES_COLLECTION,
            "research_context": self.RESEARCH_COLLECTION,
        }

        if collection_name not in valid_names:
            return json.dumps({"error": f"Invalid collection: {collection_name}"})

        self.client.delete_collection(valid_names[collection_name])
        self._ensure_collections()

        return json.dumps({"success": True, "cleared": collection_name})
