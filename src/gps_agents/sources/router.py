"""Smart router for unified search across multiple genealogy sources.

Provides intelligent routing based on region, record type, and availability,
with parallel search execution and result aggregation.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, Field

from gps_agents.models.search import RawRecord, SearchQuery

if TYPE_CHECKING:
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
    CEMETERY = "cemetery"
    CENSUS = "census"
    IMMIGRATION = "immigration"
    EMIGRATION = "emigration"
    MILITARY = "military"
    PROBATE = "probate"
    LAND = "land"
    CHURCH = "church"
    CIVIL = "civil"
    NEWSPAPER = "newspaper"
    OBITUARY = "obituary"
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
    error_details: dict | None = None  # Structured error info (e.g., timeout_seconds)


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
    max_concurrent_searches: int = Field(default=4, description="Max concurrent source queries")
    start_jitter_seconds: float = Field(default=0.2, description="Random start jitter per task")


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
    REGION_SOURCES: ClassVar[dict[Region, list[str]]] = {
        Region.BELGIUM: ["familysearch", "geneanet", "belgian_archives", "wikitree"],
        Region.NETHERLANDS: ["familysearch", "geneanet", "wikitree"],
        Region.GERMANY: ["familysearch", "geneanet", "wikitree"],
        Region.FRANCE: ["familysearch", "geneanet", "wikitree"],
        Region.IRELAND: ["familysearch", "findmypast", "wikitree"],
        Region.SCOTLAND: ["familysearch", "findmypast", "wikitree"],
        Region.ENGLAND: ["familysearch", "findmypast", "wikitree", "findagrave", "freebmd"],
        Region.WALES: ["familysearch", "findmypast", "wikitree", "freebmd"],
        Region.CHANNEL_ISLANDS: ["jerripedia", "familysearch", "wikitree"],
        Region.USA: ["familysearch", "wikitree", "findagrave", "accessgenealogy", "usgenweb", "fold3", "rootsweb", "nara1950", "nara1940"],
        Region.CANADA: ["familysearch", "wikitree", "findagrave"],
        Region.WORLDWIDE: ["familysearch", "wikitree", "geneanet", "findagrave"],
    }

    # Source recommendations by record type
    RECORD_TYPE_SOURCES: ClassVar[dict[RecordType, list[str]]] = {
        RecordType.BURIAL: ["findagrave", "familysearch", "accessgenealogy", "usgenweb"],
        RecordType.CEMETERY: ["findagrave", "accessgenealogy", "usgenweb"],
        RecordType.DEATH: ["findagrave", "familysearch", "geneanet", "rootsweb"],
        RecordType.BIRTH: ["familysearch", "geneanet", "usgenweb"],
        RecordType.MARRIAGE: ["familysearch", "geneanet", "usgenweb"],
        RecordType.CENSUS: ["familysearch", "findmypast", "accessgenealogy", "usgenweb", "nara1950", "nara1940"],
        RecordType.IMMIGRATION: ["familysearch", "accessgenealogy"],
        RecordType.MILITARY: ["familysearch", "fold3", "accessgenealogy", "usgenweb"],
        RecordType.OBITUARY: ["rootsweb", "findagrave"],
        RecordType.DNA: ["wikitree"],
        RecordType.CHURCH: ["familysearch", "geneanet"],
        RecordType.LAND: ["usgenweb", "familysearch"],
        RecordType.PROBATE: ["usgenweb", "familysearch"],
    }

    def __init__(self, config: RouterConfig | None = None) -> None:
        """Initialize the search router."""
        self.config = config or RouterConfig()
        self._sources: dict[str, GenealogySource] = {}
        self._connected = False

    def register_source(self, source: GenealogySource) -> None:
        """Register a genealogy source with the router.

        Normalizes the key to lowercase to match recommendation maps.
        """
        key = getattr(source, "name", str(source)).lower()
        self._sources[key] = source

    def unregister_source(self, source_name: str) -> None:
        """Remove a source from the router."""
        self._sources.pop(source_name.lower(), None)

    @property
    def available_sources(self) -> list[str]:
        """Get list of registered source names."""
        return list(self._sources.keys())

    def get_recommended_sources(
        self,
        region: Region | None = None,
        record_type: RecordType | None = None,
        record_types: list[str] | None = None,
    ) -> list[str]:
        """Get recommended sources for a region and/or record type(s).

        Computes: recommended = region_sources ∪ union_of_sources_for_each(record_type)

        Args:
            region: Geographic region to search
            record_type: Single type of record to find (deprecated, use record_types)
            record_types: List of record type names to find

        Returns:
            List of source names to search, deterministically ordered
        """
        recommended = set()

        # Add region-specific sources
        if region:
            recommended.update(self.REGION_SOURCES.get(region, []))

        # Add single record_type sources (backward compatibility)
        if record_type:
            recommended.update(self.RECORD_TYPE_SOURCES.get(record_type, []))

        # Add sources for each record type in the list
        if record_types:
            for rt_name in record_types:
                try:
                    rt = RecordType(rt_name.lower())
                    recommended.update(self.RECORD_TYPE_SOURCES.get(rt, []))
                except ValueError:
                    # Unknown record type, skip
                    pass

        if not recommended:
            # Default to worldwide sources
            recommended.update(self.REGION_SOURCES[Region.WORLDWIDE])

        # Filter to only registered sources and sort deterministically
        available = [s for s in recommended if s in self._sources]
        return sorted(available)  # Deterministic ordering

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
        elif region or query.record_types:
            # Use record-type-aware routing: region_sources ∪ record_type_sources
            recommended = self.get_recommended_sources(
                region=region,
                record_types=query.record_types,
            )
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

    def _get_stable_jitter(self, name: str) -> float:
        """Calculate deterministic jitter based on source name.

        Uses MD5 hash for stable, reproducible jitter across runs.
        """
        stable_hash = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
        return min(self.config.start_jitter_seconds, 1.0) * (stable_hash % 5) / 5

    async def _search_parallel(
        self,
        query: SearchQuery,
        sources: dict[str, GenealogySource],
    ) -> dict[str, SourceSearchResult]:
        """Execute searches in parallel."""

        sem = asyncio.Semaphore(self.config.max_concurrent_searches)

        async def search_one(name: str, source: GenealogySource) -> tuple[str, SourceSearchResult]:
            start = time.time()
            try:
                # Stagger task start to avoid bursts
                await asyncio.sleep(self._get_stable_jitter(name))
                async with sem:
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
            except (asyncio.TimeoutError, TimeoutError):
                return name, SourceSearchResult(
                    source_name=name,
                    records=[],
                    total_count=0,
                    search_time_ms=(time.time() - start) * 1000,
                    error="timeout",
                    error_details={"timeout_seconds": self.config.timeout_per_source},
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
        """Execute searches sequentially with per-source timeout."""
        results = {}

        for name, source in sources.items():
            start = time.time()
            try:
                records = await asyncio.wait_for(
                    source.search(query),
                    timeout=self.config.timeout_per_source,
                )
                if len(records) > self.config.max_results_per_source:
                    records = records[:self.config.max_results_per_source]

                results[name] = SourceSearchResult(
                    source_name=name,
                    records=records,
                    total_count=len(records),
                    search_time_ms=(time.time() - start) * 1000,
                )
            except (asyncio.TimeoutError, TimeoutError):
                results[name] = SourceSearchResult(
                    source_name=name,
                    records=[],
                    total_count=0,
                    search_time_ms=(time.time() - start) * 1000,
                    error="timeout",
                    error_details={"timeout_seconds": self.config.timeout_per_source},
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
        """Remove duplicate records using multi-tier deduplication.

        Uses three levels of deduplication keys:
        1. URL (most specific - same URL = definitely same record)
        2. Source + record_id (traditional approach)
        3. Content fingerprint (catches cross-source duplicates)
        """
        seen_urls: set[str] = set()
        seen_source_ids: set[tuple[str, str]] = set()
        seen_fingerprints: set[str] = set()
        unique = []

        for record in records:
            # Level 1: URL-based dedup (highest priority)
            if record.url:
                normalized_url = self._normalize_url(record.url)
                if normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)

            # Level 2: Source + record_id
            source_id_key = (record.source, record.record_id)
            if source_id_key in seen_source_ids:
                continue
            seen_source_ids.add(source_id_key)

            # Level 3: Content fingerprint (catches cross-source duplicates)
            fingerprint = self._compute_record_fingerprint(record)
            if fingerprint and fingerprint in seen_fingerprints:
                continue
            if fingerprint:
                seen_fingerprints.add(fingerprint)

            unique.append(record)

        return unique

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication comparison."""
        # Remove protocol, trailing slashes, query params for comparison
        normalized = url.lower()
        for prefix in ("https://", "http://", "www."):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        return normalized.rstrip("/").split("?")[0]

    def _compute_record_fingerprint(self, record: RawRecord) -> str | None:
        """Compute content fingerprint for cross-source deduplication.

        Creates a stable hash from key identifying fields.
        """
        fields = record.extracted_fields
        if not fields:
            return None

        # Extract key identifying information
        parts = []
        for key in ("full_name", "given_name", "surname", "birth_date", "birth_year", "birth_place"):
            val = fields.get(key)
            if val:
                # Normalize: lowercase, strip whitespace, remove punctuation
                normalized = str(val).lower().strip()
                parts.append(f"{key}:{normalized}")

        if len(parts) < 2:
            # Not enough identifying info for reliable fingerprint
            return None

        # Create stable hash
        content = "|".join(sorted(parts))
        return hashlib.md5(content.encode()).hexdigest()

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
    return SearchRouter(config)
