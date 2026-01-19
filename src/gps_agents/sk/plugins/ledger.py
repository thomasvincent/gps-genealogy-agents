"""Semantic Kernel plugin for the Fact Ledger."""

import json
from typing import Annotated
from uuid import UUID

from semantic_kernel.functions import kernel_function

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.models.fact import Fact, FactStatus
from gps_agents.projections.sqlite_projection import SQLiteProjection


class LedgerPlugin:
    """Plugin for interacting with the immutable fact ledger.

    This plugin provides read/write access to the append-only fact ledger.
    Only the workflow_agent should have write permissions in practice.
    """

    def __init__(self, ledger: FactLedger, projection: SQLiteProjection) -> None:
        self.ledger = ledger
        self.projection = projection

    @kernel_function(
        name="append_fact",
        description="Append a new fact or fact version to the immutable ledger. Only workflow_agent should call this.",
    )
    def append_fact(
        self,
        fact_json: Annotated[str, "JSON representation of the Fact to append"],
    ) -> Annotated[str, "Ledger key of the appended fact"]:
        """Append a fact to the ledger."""
        fact = Fact.model_validate_json(fact_json)
        key = self.ledger.append(fact)
        # Update projection for querying
        self.projection.upsert_fact(fact)
        return json.dumps({"success": True, "key": key, "fact_id": str(fact.fact_id)})

    @kernel_function(
        name="get_fact",
        description="Retrieve a fact by ID, optionally at a specific version.",
    )
    def get_fact(
        self,
        fact_id: Annotated[str, "UUID of the fact to retrieve"],
        version: Annotated[int | None, "Specific version to retrieve, or None for latest"] = None,
    ) -> Annotated[str, "JSON representation of the fact, or error message"]:
        """Get a fact from the ledger."""
        try:
            fact = self.ledger.get(UUID(fact_id), version)
            if fact is None:
                return json.dumps({"error": "Fact not found", "fact_id": fact_id})
            return fact.model_dump_json()
        except ValueError as e:
            return json.dumps({"error": f"Invalid UUID: {e}"})

    @kernel_function(
        name="get_fact_history",
        description="Get all versions of a fact to see its evolution.",
    )
    def get_fact_history(
        self,
        fact_id: Annotated[str, "UUID of the fact"],
    ) -> Annotated[str, "JSON array of all fact versions"]:
        """Get the complete history of a fact."""
        try:
            versions = self.ledger.get_all_versions(UUID(fact_id))
            return json.dumps([f.model_dump(mode="json") for f in versions])
        except ValueError as e:
            return json.dumps({"error": f"Invalid UUID: {e}"})

    @kernel_function(
        name="list_facts_by_status",
        description="List facts filtered by their status (proposed, accepted, rejected, incomplete).",
    )
    def list_facts_by_status(
        self,
        status: Annotated[str, "Status to filter by: proposed, accepted, rejected, or incomplete"],
        limit: Annotated[int, "Maximum number of facts to return"] = 50,
    ) -> Annotated[str, "JSON array of facts matching the status"]:
        """List facts with a specific status."""
        try:
            fact_status = FactStatus(status.lower())
            facts = list(self.ledger.iter_all_facts(fact_status))[:limit]
            return json.dumps([f.model_dump(mode="json") for f in facts])
        except ValueError:
            return json.dumps({"error": f"Invalid status: {status}"})

    @kernel_function(
        name="search_facts",
        description="Search facts using the projection database.",
    )
    def search_facts(
        self,
        query: Annotated[str, "Search query string"],
        status: Annotated[str | None, "Optional status filter"] = None,
        limit: Annotated[int, "Maximum results"] = 20,
    ) -> Annotated[str, "JSON array of matching facts"]:
        """Search facts in the projection."""
        fact_status = FactStatus(status.upper()) if status else None
        results = self.projection.search_facts(query, fact_status, limit)
        return json.dumps(results)

    @kernel_function(
        name="get_ledger_stats",
        description="Get statistics about the fact ledger.",
    )
    def get_ledger_stats(self) -> Annotated[str, "JSON object with ledger statistics"]:
        """Get ledger statistics."""
        total = self.ledger.count()
        stats = {
            "total_facts": total,
            "by_status": {},
        }
        for status in FactStatus:
            count = len(list(self.ledger.iter_all_facts(status)))
            stats["by_status"][status.value] = count
        return json.dumps(stats)

    @kernel_function(
        name="update_fact_status",
        description="Create a new version of a fact with updated status. Only workflow_agent should call this.",
    )
    def update_fact_status(
        self,
        fact_id: Annotated[str, "UUID of the fact to update"],
        new_status: Annotated[str, "New status: accepted, rejected, or incomplete"],
    ) -> Annotated[str, "JSON with the new fact version"]:
        """Update fact status by creating a new version."""
        try:
            fact = self.ledger.get(UUID(fact_id))
            if fact is None:
                return json.dumps({"error": "Fact not found"})

            new_fact = fact.set_status(FactStatus(new_status.lower()))
            key = self.ledger.append(new_fact)
            self.projection.upsert_fact(new_fact)

            return json.dumps({
                "success": True,
                "key": key,
                "new_version": new_fact.version,
                "status": new_status.lower(),
            })
        except ValueError as e:
            return json.dumps({"error": str(e)})
