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
    # US State-level regions (for specialized sources)
    CALIFORNIA = "california"
    OKLAHOMA = "oklahoma"
    NORTH_CAROLINA = "north_carolina"


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
    # Specialized record types
    TRIBAL = "tribal"  # Native American tribal enrollment records
    FREEDMEN = "freedmen"  # Cherokee/Creek/etc Freedmen records
    OTHER = "other"


# Keywords that suggest Freedmen/Native American research context
FREEDMEN_CONTEXT_KEYWORDS = frozenset([
    "oklahoma", "indian territory", "cherokee", "creek", "muscogee",
    "choctaw", "chickasaw", "seminole", "freedmen", "freedman",
    "dawes", "tribal", "five civilized tribes", "vinita", "muskogee",
    "tahlequah", "mcalester", "ardmore", "durant", "tishomingo",
])

# Place names strongly associated with Five Civilized Tribes territory
INDIAN_TERRITORY_PLACES = frozenset([
    "vinita", "tahlequah", "muskogee", "okmulgee", "mcalester",
    "ardmore", "durant", "tishomingo", "wewoka", "anadarko",
    "thlequah", "claremore", "nowata", "pryor", "wagoner",
])


def detect_freedmen_context(query: "SearchQuery") -> bool:
    """Detect if a query might involve Freedmen/Native American records.

    Looks for contextual clues in birth_place, death_place, or notes
    that suggest the ancestor may have been enrolled in tribal rolls.

    Args:
        query: The search query to analyze

    Returns:
        True if Freedmen/tribal sources should be prioritized
    """
    search_text = ""

    # Gather all location and context text from query
    for field in [query.birth_place, query.death_place]:
        if field:
            search_text += f" {field}"

    # Check for explicit record types
    if query.record_types:
        if "tribal" in query.record_types or "freedmen" in query.record_types:
            return True

    # Normalize and check for keywords
    search_lower = search_text.lower()

    # Check for direct keyword matches
    for keyword in FREEDMEN_CONTEXT_KEYWORDS:
        if keyword in search_lower:
            return True

    # Check for Indian Territory place names
    words = search_lower.split()
    for word in words:
        word_clean = word.strip(".,;:()")
        if word_clean in INDIAN_TERRITORY_PLACES:
            return True

    return False


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
class EntityCluster:
    """A cluster of records representing the same person entity."""
    cluster_id: str
    fingerprint: str
    records: list[RawRecord] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)
    confidence: float = 0.0

    # Best estimate fields derived from cluster
    best_name: str | None = None
    best_birth_year: int | None = None
    best_birth_place: str | None = None
    best_death_year: int | None = None

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def source_count(self) -> int:
        return len(self.sources)


@dataclass
class UnifiedSearchResult:
    """Combined result from multiple sources."""
    query: SearchQuery
    results: list[RawRecord] = field(default_factory=list)
    by_source: dict[str, SourceSearchResult] = field(default_factory=dict)
    sources_searched: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    total_search_time_ms: float = 0.0
    # Entity clusters (grouped records representing same person)
    entity_clusters: list[EntityCluster] = field(default_factory=list)


class ErrorType(str, Enum):
    """Error taxonomy for resilience tracking."""
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    TRANSIENT = "transient"  # Network errors, 5xx, etc.
    PERMANENT = "permanent"  # 4xx (not auth), bad request, etc.
    UNKNOWN = "unknown"


@dataclass
class SourceMetrics:
    """Metrics tracking for a single source."""
    total_searches: int = 0
    successful_searches: int = 0
    failed_searches: int = 0
    total_records_returned: int = 0
    total_latency_ms: float = 0.0
    error_counts: dict[str, int] = field(default_factory=dict)
    last_error: str | None = None
    last_success_time: float | None = None
    circuit_open: bool = False
    circuit_open_until: float | None = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_searches == 0:
            return 1.0
        return self.successful_searches / self.total_searches

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        if self.successful_searches == 0:
            return 0.0
        return self.total_latency_ms / self.successful_searches


class RouterConfig(BaseModel):
    """Configuration for the search router."""
    parallel: bool = Field(default=True, description="Search sources in parallel")
    timeout_per_source: float = Field(default=30.0, description="Timeout per source in seconds")
    max_results_per_source: int = Field(default=50, description="Max results per source")
    deduplicate: bool = Field(default=True, description="Remove duplicate records")
    sort_by_confidence: bool = Field(default=True, description="Sort results by confidence")
    max_concurrent_searches: int = Field(default=4, description="Max concurrent source queries")
    start_jitter_seconds: float = Field(default=0.2, description="Random start jitter per task")

    # Two-pass search configuration
    first_pass_source_limit: int = Field(default=5, description="Max sources for first pass")
    second_pass_enabled: bool = Field(default=True, description="Enable second pass if confidence low")
    second_pass_confidence_threshold: float = Field(default=0.7, description="Below this, expand search")

    # Resilience configuration
    retry_transient_errors: bool = Field(default=True, description="Retry transient errors")
    max_retries: int = Field(default=2, description="Max retries per source")
    retry_backoff_base: float = Field(default=1.0, description="Base backoff in seconds")
    circuit_breaker_enabled: bool = Field(default=True, description="Enable circuit breaker")
    circuit_breaker_threshold: int = Field(default=3, description="Failures before opening circuit")
    circuit_breaker_reset_seconds: float = Field(default=60.0, description="Time before circuit reset")


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
        # California - comprehensive regional sources
        Region.CALIFORNIA: [
            "familysearch", "wikitree", "findagrave",
            # Tri-Valley (Livermore, Pleasanton, Dublin)
            "trivalleygenealogy", "lags", "bunshahindex", "pleasantonweekly", "calisphere",
            # Gold Country (Highway 49 corridor)
            "goldcountry", "eldoradocounty", "tuolumnecounty", "placercounty", "mariposacounty", "nevadacounty",
            # Ventura County
            "venturacounty", "venturacountygenealogy", "oxnardlibrary", "museumventuracounty",
            # Los Angeles County
            "losangelescounty", "altadenahistoricalsociety", "laplgenealogy", "huntingtonlibrary", "uscdigitallibrary",
            # Pasadena
            "pasadenanewsindex", "lacountynewspapers",
        ],
        # Oklahoma - Native American records, vital records, historical society
        Region.OKLAHOMA: [
            "familysearch", "wikitree", "findagrave",
            # Oklahoma state sources
            "oklahomageology", "oklahomahistoricalsociety", "oklahomavitalrecords",
            "oklahomanativeamerican",
            # African American records (significant for OK history)
            "accessgenealogy", "africanamericangenealogy",
        ],
        # North Carolina - Wake/Durham Counties, vital records, African American
        Region.NORTH_CAROLINA: [
            "familysearch", "wikitree", "findagrave",
            # NC state sources
            "northcarolinageology", "ncstatearchives", "ncvitalrecords",
            "ncafricanamerican", "nccountyrecords",
            # African American records (significant for NC history)
            "accessgenealogy", "africanamericangenealogy", "freedmansbureau",
        ],
    }

    # Source recommendations by record type
    RECORD_TYPE_SOURCES: ClassVar[dict[RecordType, list[str]]] = {
        RecordType.BURIAL: ["findagrave", "familysearch", "accessgenealogy", "usgenweb"],
        RecordType.CEMETERY: ["findagrave", "accessgenealogy", "usgenweb"],
        RecordType.DEATH: [
            "findagrave", "familysearch", "geneanet", "rootsweb",
            # California regional death indices
            "venturacountygenealogy",  # 80,000+ death records
            "goldcountry", "nevadacounty",  # Gold Country obituary/death indices
            # Oklahoma death index (1908-1969 free via FamilySearch)
            "oklahomavitalrecords",
            # North Carolina death certificates (1906-1994 free via FamilySearch)
            "ncvitalrecords",
        ],
        RecordType.BIRTH: [
            "familysearch", "geneanet", "usgenweb",
            # Oklahoma birth records (restricted)
            "oklahomavitalrecords",
            # North Carolina birth records (delayed birth certificates)
            "ncvitalrecords",
        ],
        RecordType.MARRIAGE: [
            "familysearch", "geneanet", "usgenweb",
            # Oklahoma marriage records (1890-present)
            "oklahomavitalrecords",
            # North Carolina marriage records (1868-present)
            "ncvitalrecords", "nccountyrecords",
        ],
        RecordType.CENSUS: ["familysearch", "findmypast", "accessgenealogy", "usgenweb", "nara1950", "nara1940"],
        RecordType.IMMIGRATION: ["familysearch", "accessgenealogy"],
        RecordType.MILITARY: ["familysearch", "fold3", "accessgenealogy", "usgenweb"],
        RecordType.OBITUARY: [
            "rootsweb", "findagrave", "pasadenanewsindex", "lacountynewspapers",
            "pleasantonweekly", "lags",
            # California regional obituary/newspaper sources
            "trivalleygenealogy", "bunshahindex",
            "goldcountry", "nevadacounty",  # Searls Library 265,000+ names
            "venturacounty", "museumventuracounty",  # Press-Courier morgue
            "losangelescounty", "laplgenealogy", "uscdigitallibrary",  # LA Examiner
        ],
        RecordType.NEWSPAPER: [
            "pasadenanewsindex", "lacountynewspapers", "bunshahindex", "trivalleygenealogy",
            # California regional newspaper sources
            "goldcountry", "eldoradocounty", "tuolumnecounty", "placercounty",
            "venturacounty", "museumventuracounty",
            "losangelescounty", "laplgenealogy", "uscdigitallibrary",  # 1.4M LA Examiner photos
        ],
        RecordType.DNA: ["wikitree"],
        RecordType.CHURCH: [
            "familysearch", "geneanet",
            "huntingtonlibrary",  # ECPP - 250,000+ mission records 1769-1850
        ],
        RecordType.LAND: ["usgenweb", "familysearch", "venturacountygenealogy"],  # VCGS land indices
        RecordType.PROBATE: ["usgenweb", "familysearch"],
        # Native American and Freedmen records
        RecordType.TRIBAL: [
            "ohsdawesrolls",  # OHS Dawes Rolls Final Rolls (searchable)
            "oklahomanativeamerican",  # Oklahoma Native American records
            "familysearch",  # FamilySearch Five Civilized Tribes collections
            "accessgenealogy",  # Dawes Rolls transcriptions
            "oklahomageology",  # Combined Oklahoma sources
        ],
        RecordType.FREEDMEN: [
            "ohsdawesrolls",  # OHS Dawes Rolls (includes Freedmen enrollees)
            "oklahomanativeamerican",  # Native American records (Freedmen sections)
            "familysearch",  # Cherokee/Creek/etc Freedmen collections
            "freedmansbureau",  # Freedman's Bureau records
            "africanamericangenealogy",  # African American genealogy
            "accessgenealogy",  # Dawes Rolls and Freedmen transcriptions
        ],
    }

    # Additional Freedmen-specific FamilySearch collections to recommend
    FREEDMEN_FAMILYSEARCH_COLLECTIONS: ClassVar[list[str]] = [
        "five_civilized_tribes",  # 1852353 - Enrollment applications (includes rejected)
        "cherokee_freedmen",  # 1916102
        "creek_freedmen",  # 1916103
        "choctaw_freedmen",  # 1916090
        "chickasaw_freedmen",  # 1916089
        "seminole_freedmen",  # 1916110
        "indian_census_rolls",  # 1914530 - Indian Census Rolls 1885-1940
        "dawes_packets",  # 1913517 - Detailed enrollment packets
    ]

    def __init__(self, config: RouterConfig | None = None) -> None:
        """Initialize the search router."""
        self.config = config or RouterConfig()
        self._sources: dict[str, GenealogySource] = {}
        self._connected = False
        self._metrics: dict[str, SourceMetrics] = {}  # Per-source metrics

    def register_source(self, source: GenealogySource) -> None:
        """Register a genealogy source with the router.

        Normalizes the key to lowercase to match recommendation maps.
        """
        key = getattr(source, "name", str(source)).lower()
        self._sources[key] = source
        self._metrics[key] = SourceMetrics()

    def unregister_source(self, source_name: str) -> None:
        """Remove a source from the router."""
        key = source_name.lower()
        self._sources.pop(key, None)
        self._metrics.pop(key, None)

    def get_metrics(self, source_name: str | None = None) -> dict[str, SourceMetrics] | SourceMetrics | None:
        """Get metrics for source(s).

        Args:
            source_name: Optional specific source. None returns all.

        Returns:
            Metrics dict or single SourceMetrics
        """
        if source_name:
            return self._metrics.get(source_name.lower())
        return self._metrics.copy()

    @property
    def available_sources(self) -> list[str]:
        """Get list of registered source names."""
        return list(self._sources.keys())

    def get_recommended_sources(
        self,
        region: Region | None = None,
        record_type: RecordType | None = None,
        record_types: list[str] | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """Get recommended sources for a region and/or record type(s).

        Ranks sources by priority:
        1. Sources matching BOTH region AND record_type (highest priority)
        2. Sources matching region only
        3. Sources matching record_type only

        Args:
            region: Geographic region to search
            record_type: Single type of record to find (deprecated, use record_types)
            record_types: List of record type names to find
            limit: Max sources to return (None = no limit)

        Returns:
            List of source names to search, ranked by priority then deterministically ordered
        """
        # Gather sources from region
        region_sources = set()
        if region:
            region_sources.update(self.REGION_SOURCES.get(region, []))

        # Gather sources from record types
        record_type_sources = set()
        if record_type:
            record_type_sources.update(self.RECORD_TYPE_SOURCES.get(record_type, []))

        if record_types:
            for rt_name in record_types:
                try:
                    rt = RecordType(rt_name.lower())
                    record_type_sources.update(self.RECORD_TYPE_SOURCES.get(rt, []))
                except ValueError:
                    pass

        # Build priority tiers
        # Tier 1: Both region AND record_type match
        tier1 = region_sources & record_type_sources

        # Tier 2: Region only (not in tier 1)
        tier2 = region_sources - tier1

        # Tier 3: Record type only (not in tier 1)
        tier3 = record_type_sources - tier1

        # Combine tiers in priority order
        ranked: list[str] = []
        for tier in [tier1, tier2, tier3]:
            # Within each tier, sort deterministically
            ranked.extend(sorted(tier))

        # If no recommendations, default to worldwide
        if not ranked:
            ranked = sorted(self.REGION_SOURCES[Region.WORLDWIDE])

        # Filter to only registered sources (preserve priority order)
        available = [s for s in ranked if s in self._sources]

        # Apply limit if specified
        if limit and len(available) > limit:
            available = available[:limit]

        return available

    def rank_sources_for_query(
        self,
        query: SearchQuery,
        region: Region | None = None,
    ) -> list[tuple[str, int]]:
        """Rank sources for a specific query with priority scores.

        Returns:
            List of (source_name, priority_score) tuples, highest score first.
            Priority scores: 3 = region+type, 2 = region, 1 = type, 0 = default
        """
        region_sources = set()
        if region:
            region_sources.update(self.REGION_SOURCES.get(region, []))

        record_type_sources = set()
        if query.record_types:
            for rt_name in query.record_types:
                try:
                    rt = RecordType(rt_name.lower())
                    record_type_sources.update(self.RECORD_TYPE_SOURCES.get(rt, []))
                except ValueError:
                    pass

        ranked = []
        for source_name in self._sources:
            in_region = source_name in region_sources
            in_record_type = source_name in record_type_sources

            if in_region and in_record_type:
                priority = 3
            elif in_region:
                priority = 2
            elif in_record_type:
                priority = 1
            else:
                priority = 0

            ranked.append((source_name, priority))

        # Sort by priority (desc), then name (asc) for determinism
        ranked.sort(key=lambda x: (-x[1], x[0]))
        return ranked

    async def search(
        self,
        query: SearchQuery,
        sources: list[str] | None = None,
        region: Region | None = None,
        two_pass: bool | None = None,
        auto_detect_freedmen: bool = True,
    ) -> UnifiedSearchResult:
        """Execute a unified search across multiple sources.

        Supports two-pass search:
        - Pass 1 (Recall): Search limited sources with broad query
        - Pass 2 (Precision): If confidence low, expand to more sources

        Also supports automatic Freedmen/tribal record detection:
        - Detects Oklahoma/Indian Territory context
        - Automatically includes tribal enrollment sources
        - Prioritizes Dawes Rolls and Freedmen collections

        Args:
            query: Search parameters
            sources: Specific sources to search (None = auto-select)
            region: Region for source recommendation
            two_pass: Override config for two-pass search
            auto_detect_freedmen: Auto-detect and include Freedmen sources (default True)

        Returns:
            UnifiedSearchResult with aggregated records
        """
        start_time = time.time()
        enable_two_pass = two_pass if two_pass is not None else self.config.second_pass_enabled

        # Auto-detect Freedmen context and augment query record types if needed
        effective_record_types = list(query.record_types) if query.record_types else []
        freedmen_detected = False

        if auto_detect_freedmen and detect_freedmen_context(query):
            freedmen_detected = True
            # Add tribal/freedmen record types if not already present
            if "tribal" not in effective_record_types:
                effective_record_types.append("tribal")
            if "freedmen" not in effective_record_types:
                effective_record_types.append("freedmen")
            # Also set region to Oklahoma if not specified
            if region is None:
                region = Region.OKLAHOMA

        # Create effective query with augmented record types
        effective_query = SearchQuery(
            surname=query.surname,
            given_name=query.given_name,
            birth_year=query.birth_year,
            birth_place=query.birth_place,
            death_year=query.death_year,
            death_place=query.death_place,
            record_types=effective_record_types,  # Already a list, keep as list (not None)
            exclude_sources=query.exclude_sources,
        )

        # Determine which sources to search
        if sources:
            first_pass_sources = {k: v for k, v in self._sources.items() if k in sources}
            all_possible_sources = first_pass_sources  # No expansion if explicit sources
        elif region or effective_query.record_types:
            # Use record-type-aware routing with priority ranking
            recommended = self.get_recommended_sources(
                region=region,
                record_types=effective_query.record_types,
                limit=self.config.first_pass_source_limit if enable_two_pass else None,
            )
            first_pass_sources = {k: v for k, v in self._sources.items() if k in recommended}

            # Get all possible sources for second pass (no limit)
            all_recommended = self.get_recommended_sources(
                region=region,
                record_types=effective_query.record_types,
                limit=None,
            )
            all_possible_sources = {k: v for k, v in self._sources.items() if k in all_recommended}
        else:
            first_pass_sources = self._sources
            all_possible_sources = self._sources

        # Filter out sources in exclude list
        if query.exclude_sources:
            first_pass_sources = {
                k: v for k, v in first_pass_sources.items()
                if k not in query.exclude_sources
            }
            all_possible_sources = {
                k: v for k, v in all_possible_sources.items()
                if k not in query.exclude_sources
            }

        # Filter out sources with open circuit breakers
        first_pass_sources = self._filter_circuit_breakers(first_pass_sources)

        # Execute first pass
        if self.config.parallel:
            source_results = await self._search_parallel(query, first_pass_sources)
        else:
            source_results = await self._search_sequential(query, first_pass_sources)

        # Check if we need second pass
        if enable_two_pass:
            confidence = self._estimate_result_confidence(source_results)
            if confidence < self.config.second_pass_confidence_threshold:
                # Execute second pass with remaining sources
                second_pass_sources = {
                    k: v for k, v in all_possible_sources.items()
                    if k not in source_results
                }
                second_pass_sources = self._filter_circuit_breakers(second_pass_sources)

                if second_pass_sources:
                    if self.config.parallel:
                        more_results = await self._search_parallel(query, second_pass_sources)
                    else:
                        more_results = await self._search_sequential(query, second_pass_sources)
                    source_results.update(more_results)

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

        # Cluster records into person entities
        entity_clusters = self._cluster_records(all_records)

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
            entity_clusters=entity_clusters,
        )

    def _filter_circuit_breakers(
        self,
        sources: dict[str, GenealogySource],
    ) -> dict[str, GenealogySource]:
        """Filter out sources with open circuit breakers."""
        if not self.config.circuit_breaker_enabled:
            return sources

        current_time = time.time()
        filtered = {}

        for name, source in sources.items():
            metrics = self._metrics.get(name)
            if metrics and metrics.circuit_open:
                # Check if circuit should reset
                if metrics.circuit_open_until and current_time >= metrics.circuit_open_until:
                    metrics.circuit_open = False
                    metrics.circuit_open_until = None
                else:
                    continue  # Skip this source
            filtered[name] = source

        return filtered

    def _estimate_result_confidence(self, results: dict[str, SourceSearchResult]) -> float:
        """Estimate overall confidence from search results."""
        if not results:
            return 0.0

        total_records = 0
        successful_sources = 0

        for result in results.values():
            if not result.error:
                successful_sources += 1
                total_records += len(result.records)

        if successful_sources == 0:
            return 0.0

        # Heuristic: confidence based on records found and sources succeeded
        record_factor = min(1.0, total_records / 10)  # Cap at 10 records
        source_factor = successful_sources / len(results)

        return (record_factor + source_factor) / 2

    def _classify_error(self, error: str) -> ErrorType:
        """Classify an error string into ErrorType category."""
        error_lower = error.lower()

        if "timeout" in error_lower:
            return ErrorType.TIMEOUT
        if "rate limit" in error_lower or "429" in error_lower or "too many" in error_lower:
            return ErrorType.RATE_LIMIT
        if "auth" in error_lower or "401" in error_lower or "403" in error_lower or "credential" in error_lower:
            return ErrorType.AUTH
        if "500" in error_lower or "502" in error_lower or "503" in error_lower or "504" in error_lower:
            return ErrorType.TRANSIENT
        if "connect" in error_lower or "network" in error_lower or "dns" in error_lower:
            return ErrorType.TRANSIENT
        if "400" in error_lower or "404" in error_lower or "invalid" in error_lower:
            return ErrorType.PERMANENT

        return ErrorType.UNKNOWN

    def _is_retryable_error(self, error_type: ErrorType) -> bool:
        """Determine if an error type is retryable."""
        return error_type in {ErrorType.TIMEOUT, ErrorType.TRANSIENT, ErrorType.RATE_LIMIT}

    def _update_metrics(
        self,
        source_name: str,
        success: bool,
        latency_ms: float,
        record_count: int = 0,
        error: str | None = None,
    ) -> None:
        """Update metrics for a source after a search."""
        metrics = self._metrics.get(source_name)
        if not metrics:
            return

        metrics.total_searches += 1

        if success:
            metrics.successful_searches += 1
            metrics.total_records_returned += record_count
            metrics.total_latency_ms += latency_ms
            metrics.last_success_time = time.time()
        else:
            metrics.failed_searches += 1
            metrics.last_error = error

            if error:
                error_type = self._classify_error(error).value
                metrics.error_counts[error_type] = metrics.error_counts.get(error_type, 0) + 1

            # Check circuit breaker threshold
            if self.config.circuit_breaker_enabled:
                recent_failures = metrics.failed_searches
                if recent_failures >= self.config.circuit_breaker_threshold:
                    metrics.circuit_open = True
                    metrics.circuit_open_until = time.time() + self.config.circuit_breaker_reset_seconds

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
        """Execute searches in parallel with retry support and metrics tracking."""

        sem = asyncio.Semaphore(self.config.max_concurrent_searches)

        async def search_one(name: str, source: GenealogySource) -> tuple[str, SourceSearchResult]:
            start = time.time()
            last_error: str | None = None
            attempts = 0
            max_attempts = 1 + (self.config.max_retries if self.config.retry_transient_errors else 0)

            while attempts < max_attempts:
                attempts += 1
                try:
                    # Stagger task start to avoid bursts (only on first attempt)
                    if attempts == 1:
                        await asyncio.sleep(self._get_stable_jitter(name))
                    else:
                        # Exponential backoff on retry
                        backoff = self.config.retry_backoff_base * (2 ** (attempts - 2))
                        await asyncio.sleep(backoff)

                    async with sem:
                        records = await asyncio.wait_for(
                            source.search(query),
                            timeout=self.config.timeout_per_source,
                        )
                    # Limit results
                    if len(records) > self.config.max_results_per_source:
                        records = records[:self.config.max_results_per_source]

                    latency_ms = (time.time() - start) * 1000
                    self._update_metrics(name, success=True, latency_ms=latency_ms, record_count=len(records))

                    return name, SourceSearchResult(
                        source_name=name,
                        records=records,
                        total_count=len(records),
                        search_time_ms=latency_ms,
                    )
                except (asyncio.TimeoutError, TimeoutError):
                    last_error = "timeout"
                    error_type = ErrorType.TIMEOUT
                except Exception as e:
                    last_error = str(e)
                    error_type = self._classify_error(last_error)

                # Check if we should retry
                if attempts < max_attempts and self._is_retryable_error(error_type):
                    continue  # Retry
                break  # No more retries

            # All attempts failed
            latency_ms = (time.time() - start) * 1000
            self._update_metrics(name, success=False, latency_ms=latency_ms, error=last_error)

            error_details = {"attempts": attempts}
            if last_error == "timeout":
                error_details["timeout_seconds"] = self.config.timeout_per_source

            return name, SourceSearchResult(
                source_name=name,
                records=[],
                total_count=0,
                search_time_ms=latency_ms,
                error=last_error,
                error_details=error_details,
            )

        tasks = [search_one(name, source) for name, source in sources.items()]
        results = await asyncio.gather(*tasks)
        return dict(results)

    async def _search_sequential(
        self,
        query: SearchQuery,
        sources: dict[str, GenealogySource],
    ) -> dict[str, SourceSearchResult]:
        """Execute searches sequentially with retry support and metrics tracking."""
        results = {}

        for name, source in sources.items():
            start = time.time()
            last_error: str | None = None
            attempts = 0
            max_attempts = 1 + (self.config.max_retries if self.config.retry_transient_errors else 0)

            while attempts < max_attempts:
                attempts += 1
                try:
                    if attempts > 1:
                        # Exponential backoff on retry
                        backoff = self.config.retry_backoff_base * (2 ** (attempts - 2))
                        await asyncio.sleep(backoff)

                    records = await asyncio.wait_for(
                        source.search(query),
                        timeout=self.config.timeout_per_source,
                    )
                    if len(records) > self.config.max_results_per_source:
                        records = records[:self.config.max_results_per_source]

                    latency_ms = (time.time() - start) * 1000
                    self._update_metrics(name, success=True, latency_ms=latency_ms, record_count=len(records))

                    results[name] = SourceSearchResult(
                        source_name=name,
                        records=records,
                        total_count=len(records),
                        search_time_ms=latency_ms,
                    )
                    break  # Success, move to next source

                except (asyncio.TimeoutError, TimeoutError):
                    last_error = "timeout"
                    error_type = ErrorType.TIMEOUT
                except Exception as e:
                    last_error = str(e)
                    error_type = self._classify_error(last_error)

                # Check if we should retry
                if attempts < max_attempts and self._is_retryable_error(error_type):
                    continue  # Retry
                break  # No more retries

            # If we didn't successfully break out, record the error
            if name not in results:
                latency_ms = (time.time() - start) * 1000
                self._update_metrics(name, success=False, latency_ms=latency_ms, error=last_error)

                error_details = {"attempts": attempts}
                if last_error == "timeout":
                    error_details["timeout_seconds"] = self.config.timeout_per_source

                results[name] = SourceSearchResult(
                    source_name=name,
                    records=[],
                    total_count=0,
                    search_time_ms=latency_ms,
                    error=last_error,
                    error_details=error_details,
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

    def _cluster_records(self, records: list[RawRecord]) -> list[EntityCluster]:
        """Cluster records into person entities based on fingerprints.

        Groups records that likely represent the same person, computing
        best estimates for each cluster's key fields.
        """
        import re
        import uuid

        # Group records by fingerprint
        clusters_by_fingerprint: dict[str, list[RawRecord]] = {}
        unclustered: list[RawRecord] = []

        for record in records:
            fingerprint = self._compute_record_fingerprint(record)
            if fingerprint:
                if fingerprint not in clusters_by_fingerprint:
                    clusters_by_fingerprint[fingerprint] = []
                clusters_by_fingerprint[fingerprint].append(record)
            else:
                unclustered.append(record)

        # Build EntityCluster objects
        clusters: list[EntityCluster] = []

        for fingerprint, cluster_records in clusters_by_fingerprint.items():
            cluster = EntityCluster(
                cluster_id=str(uuid.uuid4())[:8],
                fingerprint=fingerprint,
                records=cluster_records,
                sources={r.source for r in cluster_records},
            )

            # Compute best estimates from cluster records
            cluster.best_name = self._best_value_from_records(cluster_records, ["full_name"])
            cluster.best_birth_place = self._best_value_from_records(cluster_records, ["birth_place"])

            # Extract birth year
            birth_str = self._best_value_from_records(cluster_records, ["birth_year", "birth_date"])
            if birth_str:
                year_match = re.search(r"\b(1\d{3}|20\d{2})\b", str(birth_str))
                if year_match:
                    cluster.best_birth_year = int(year_match.group(1))

            # Extract death year
            death_str = self._best_value_from_records(cluster_records, ["death_year", "death_date"])
            if death_str:
                year_match = re.search(r"\b(1\d{3}|20\d{2})\b", str(death_str))
                if year_match:
                    cluster.best_death_year = int(year_match.group(1))

            # Compute confidence based on corroboration
            base_confidence = sum(r.confidence_hint or 0.5 for r in cluster_records) / len(cluster_records)
            # Boost confidence for multi-source corroboration
            source_boost = min(0.2, 0.05 * (cluster.source_count - 1))
            cluster.confidence = min(1.0, base_confidence + source_boost)

            clusters.append(cluster)

        # Create single-record clusters for unclustered records
        for record in unclustered:
            cluster = EntityCluster(
                cluster_id=str(uuid.uuid4())[:8],
                fingerprint=f"single:{record.source}:{record.record_id}",
                records=[record],
                sources={record.source},
                confidence=record.confidence_hint or 0.5,
            )
            fields = record.extracted_fields
            cluster.best_name = fields.get("full_name")
            cluster.best_birth_place = fields.get("birth_place")

            birth_str = fields.get("birth_year") or fields.get("birth_date")
            if birth_str:
                year_match = re.search(r"\b(1\d{3}|20\d{2})\b", str(birth_str))
                if year_match:
                    cluster.best_birth_year = int(year_match.group(1))

            clusters.append(cluster)

        # Sort clusters by confidence (highest first), then by record count
        clusters.sort(key=lambda c: (-c.confidence, -c.record_count))

        return clusters

    def _best_value_from_records(
        self,
        records: list[RawRecord],
        field_names: list[str],
    ) -> str | None:
        """Get the best value for a field from multiple records.

        Prefers values from higher-confidence records.
        """
        candidates: list[tuple[str, float]] = []

        for record in records:
            confidence = record.confidence_hint or 0.5
            for field in field_names:
                val = record.extracted_fields.get(field)
                if val:
                    candidates.append((str(val), confidence))
                    break  # Use first matching field

        if not candidates:
            return None

        # Return value from highest-confidence record
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]

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

    async def search_tribal_freedmen(
        self,
        surname: str,
        given_name: str | None = None,
        birth_year: int | None = None,
        birth_place: str | None = None,
        tribe: str | None = None,
    ) -> UnifiedSearchResult:
        """Search for tribal enrollment and Freedmen records.

        Specifically targets Five Civilized Tribes records:
        - Dawes Rolls (Final Rolls 1898-1914)
        - Freedmen rolls and applications
        - Indian Census Rolls 1885-1940

        Args:
            surname: Last name to search
            given_name: Optional first name
            birth_year: Optional approximate birth year
            birth_place: Optional birth place (Oklahoma, Indian Territory, etc.)
            tribe: Optional tribe filter (cherokee, creek, choctaw, chickasaw, seminole)

        Returns:
            UnifiedSearchResult with tribal enrollment records
        """
        # Set birth_place to Oklahoma/Indian Territory if tribe specified but no place
        effective_birth_place = birth_place
        if tribe and not birth_place:
            effective_birth_place = f"{tribe.title()} Nation, Indian Territory"

        query = SearchQuery(
            surname=surname,
            given_name=given_name,
            birth_year=birth_year,
            birth_place=effective_birth_place or "Oklahoma",
            record_types=["tribal", "freedmen"],
        )
        return await self.search(query, region=Region.OKLAHOMA)

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
