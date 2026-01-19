"""Smart router for unified search across multiple genealogy sources.

Provides intelligent routing based on region, record type, and availability,
with parallel search execution and result aggregation.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field

from gps_agents.models.search import RawRecord, SearchQuery
from gps_agents.sources.base import GenealogySource


class Region(str, Enum):
    """Geographic regions for search routing."""
    BELGIUM = "belgium"
    NETHERLANDS = "netherlands"
    GERMANY = "germany"
    FRANCE = "france"
    IRELAND = "ireland"
    SCOTLAND = "scotland"
    ENGLAND = "england"
    WALES = "wales"
    CHANNEL_ISLANDS = "channel_islands"
    USA = "usa"
    CANADA = "canada"
    WORLDWIDE = "worldwide"


class RecordType(str, Enum):
    """Types of genealogical records."""
    BIRTH = "birth"
    DEATH = "death"
    MARRIAGE = "marriage"
    BURIAL = "burial"
    CENSUS = "census"
    IMMIGRATION = "immigration"
    EMIGRATION = "emigration"
    MILITARY = "military"
    PROBATE = "probate"
    LAND = "land"
    CHURCH = "church"
    CIVIL = "civil"
    NEWSPAPER = "newspaper"
    DNA = "dna"
    OTHER = "other"


@dataclass
class SourceSearchResult:
    """Result from a single source search."""
    source_name: str
    records: list[RawRecord]
    total_count: int
    search_time_ms: float
    error: str | None = None


@dataclass
class UnifiedSearchResult:
    """Combined result from multiple sources."""
    query: SearchQuery
    results: list[RawRecord] = field(default_factory=list)
    by_source: dict[str, SourceSearchResult] = field(default_factory=dict)
    sources_searched: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    total_search_time_ms: float = 0.0


class RouterConfig(BaseModel):
    """Configuration for the search router."""
    parallel: bool = Field(default=True, description="Search sources in parallel")
    timeout_per_source: float = Field(default=30.0, description="Timeout per source in seconds")
    max_results_per_source: int = Field(default=50, description="Max results per source")
    deduplicate: bool = Field(default=True, description="Remove duplicate records")
    sort_by_confidence: bool = Field(default=True, description="Sort results by confidence")


class SearchRouter:
    """
    Smart router for genealogy searches across multiple sources.

    Provides:
    - Automatic source selection based on region and record type
    - Parallel or sequential search execution
    - Result aggregation and deduplication
    - Confidence-based sorting
    """

    # Source recommendations by region
    REGION_SOURCES: dict[Region, list[str]] = {
        Region.BELGIUM: ["familysearch", "geneanet", "belgian_archives", "wikitree"],
        Region.NETHERLANDS: ["familysearch", "geneanet", "wikitree"],
        Region.GERMANY: ["familysearch", "geneanet", "wikitree"],
        Region.FRANCE: ["familysearch", "geneanet", "wikitree"],
        Region.IRELAND: ["familysearch", "findmypast", "wikitree"],
        Region.SCOTLAND: ["familysearch", "findmypast", "wikitree"],
        Region.ENGLAND: ["familysearch", "findmypast", "wikitree", "findagrave"],
        Region.WALES: ["familysearch", "findmypast", "wikitree"],
        Region.CHANNEL_ISLANDS: ["jerripedia", "familysearch", "wikitree"],
        Region.USA: ["familysearch", "wikitree", "findagrave", "accessgenealogy"],
        Region.CANADA: ["familysearch", "wikitree", "findagrave"],
        Region.WORLDWIDE: ["familysearch", "wikitree", "geneanet", "findagrave"],
    }

    # Source recommendations by record type
    RECORD_TYPE_SOURCES: dict[RecordType, list[str]] = {
        RecordType.BURIAL: ["findagrave", "familysearch"],
        RecordType.DEATH: ["findagrave", "familysearch", "geneanet"],
        RecordType.BIRTH: ["familysearch", "geneanet"],
        RecordType.MARRIAGE: ["familysearch", "geneanet"],
        RecordType.CENSUS: ["familysearch", "findmypast"],
        RecordType.IMMIGRATION: ["familysearch", "accessgenealogy"],
        RecordType.MILITARY: ["familysearch", "accessgenealogy"],
        RecordType.DNA: ["wikitree"],
        RecordType.CHURCH: ["familysearch", "geneanet"],
    }

    def __init__(self, config: RouterConfig | None = None) -> None:
        """Initialize the search router."""
        self.config = config or RouterConfig()
        self._sources: dict[str, GenealogySource] = {}
        self._connected = False

    def register_source(self, source: GenealogySource) -> None:
        """Register a genealogy source with the router."""
        self._sources[source.name] = source

    def unregister_source(self, source_name: str) -> None:
        """Remove a source from the router."""
        self._sources.pop(source_name, None)

    @property
    def available_sources(self) -> list[str]:
        """Get list of registered source names."""
        return list(self._sources.keys())

    def get_recommended_sources(
        self,
        region: Region | None = None,
        record_type: RecordType | None = None,
    ) -> list[str]:
        """Get recommended sources for a region and/or record type.

        Args:
            region: Geographic region to search
            record_type: Type of record to find

        Returns:
            List of source names to search
        """
        recommended = set()

        if region:
            recommended.update(self.REGION_SOURCES.get(region, []))

        if record_type:
            recommended.update(self.RECORD_TYPE_SOURCES.get(record_type, []))

        if not recommended:
            # Default to worldwide sources
            recommended.update(self.REGION_SOURCES[Region.WORLDWIDE])

        # Filter to only registered sources
        return [s for s in recommended if s in self._sources]

    async def search(
        self,
        query: SearchQuery,
        sources: list[str] | None = None,
        region: Region | None = None,
    ) -> UnifiedSearchResult:
        """Execute a unified search across multiple sources.

        Args:
            query: Search parameters
            sources: Specific sources to search (None = auto-select)
            region: Region for source recommendation

        Returns:
            UnifiedSearchResult with aggregated records
        """
        start_time = time.time()

        # Determine which sources to search
        if sources:
            active_sources = {k: v for k, v in self._sources.items() if k in sources}
        elif region:
            recommended = self.get_recommended_sources(region)
            active_sources = {k: v for k, v in self._sources.items() if k in recommended}
        else:
            active_sources = self._sources

        # Filter out sources in exclude list
        if query.exclude_sources:
            active_sources = {
                k: v for k, v in active_sources.items()
                if k not in query.exclude_sources
            }

        # Execute searches
        if self.config.parallel:
            source_results = await self._search_parallel(query, active_sources)
        else:
            source_results = await self._search_sequential(query, active_sources)

        # Aggregate results
        all_records = []
        sources_searched = []
        sources_failed = []

        for source_name, result in source_results.items():
            if result.error:
                sources_failed.append(source_name)
            else:
                sources_searched.append(source_name)
                all_records.extend(result.records)

        # Deduplicate if enabled
        if self.config.deduplicate:
            all_records = self._deduplicate_records(all_records)

        # Sort by confidence if enabled
        if self.config.sort_by_confidence:
            all_records.sort(
                key=lambda r: r.confidence_hint or 0.5,
                reverse=True,
            )

        total_time = (time.time() - start_time) * 1000

        return UnifiedSearchResult(
            query=query,
            results=all_records,
            by_source=source_results,
            sources_searched=sources_searched,
            sources_failed=sources_failed,
            total_search_time_ms=total_time,
        )

    async def _search_parallel(
        self,
        query: SearchQuery,
        sources: dict[str, GenealogySource],
    ) -> dict[str, SourceSearchResult]:
        """Execute searches in parallel."""

        async def search_one(name: str, source: GenealogySource) -> tuple[str, SourceSearchResult]:
            start = time.time()
            try:
                records = await asyncio.wait_for(
                    source.search(query),
                    timeout=self.config.timeout_per_source,
                )
                # Limit results
                if len(records) > self.config.max_results_per_source:
                    records = records[:self.config.max_results_per_source]

                return name, SourceSearchResult(
                    source_name=name,
                    records=records,
                    total_count=len(records),
                    search_time_ms=(time.time() - start) * 1000,
                )
            except TimeoutError:
                return name, SourceSearchResult(
                    source_name=name,
                    records=[],
                    total_count=0,
                    search_time_ms=(time.time() - start) * 1000,
                    error="Search timed out",
                )
            except Exception as e:
                return name, SourceSearchResult(
                    source_name=name,
                    records=[],
                    total_count=0,
                    search_time_ms=(time.time() - start) * 1000,
                    error=str(e),
                )

        tasks = [search_one(name, source) for name, source in sources.items()]
        results = await asyncio.gather(*tasks)
        return dict(results)

    async def _search_sequential(
        self,
        query: SearchQuery,
        sources: dict[str, GenealogySource],
    ) -> dict[str, SourceSearchResult]:
        """Execute searches sequentially."""
        results = {}

        for name, source in sources.items():
            start = time.time()
            try:
                records = await source.search(query)
                if len(records) > self.config.max_results_per_source:
                    records = records[:self.config.max_results_per_source]

                results[name] = SourceSearchResult(
                    source_name=name,
                    records=records,
                    total_count=len(records),
                    search_time_ms=(time.time() - start) * 1000,
                )
            except Exception as e:
                results[name] = SourceSearchResult(
                    source_name=name,
                    records=[],
                    total_count=0,
                    search_time_ms=(time.time() - start) * 1000,
                    error=str(e),
                )

        return results

    def _deduplicate_records(self, records: list[RawRecord]) -> list[RawRecord]:
        """Remove duplicate records based on source + record_id."""
        seen = set()
        unique = []

        for record in records:
            key = (record.source, record.record_id)
            if key not in seen:
                seen.add(key)
                unique.append(record)

        return unique

    async def search_person(
        self,
        surname: str,
        given_name: str | None = None,
        birth_year: int | None = None,
        birth_place: str | None = None,
        region: Region | None = None,
    ) -> UnifiedSearchResult:
        """Convenience method for person search."""
        query = SearchQuery(
            surname=surname,
            given_name=given_name,
            birth_year=birth_year,
            birth_place=birth_place,
        )
        return await self.search(query, region=region)

    async def search_vital_records(
        self,
        surname: str,
        given_name: str | None = None,
        birth_year: int | None = None,
        region: Region | None = None,
    ) -> UnifiedSearchResult:
        """Search for vital records (birth, death, marriage)."""
        query = SearchQuery(
            surname=surname,
            given_name=given_name,
            birth_year=birth_year,
            record_types=["birth", "death", "marriage"],
        )
        return await self.search(query, region=region)

    async def close(self) -> None:
        """Close all source connections."""
        for source in self._sources.values():
            if hasattr(source, "close"):
                await source.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False


def create_default_router(config: RouterConfig | None = None) -> SearchRouter:
    """Create a router with default sources registered.

    Note: Sources must be imported and registered separately
    as they may require configuration.
    """
    router = SearchRouter(config)
    return router
