"""Data source connectors and smart router for genealogy research."""
from __future__ import annotations

from gps_agents.models.search import RawRecord, SearchQuery
from gps_agents.sources.accessgenealogy import AccessGenealogySource
from gps_agents.sources.base import BaseSource, GenealogySource
from gps_agents.sources.familysearch import (
    FamilySearchSource,
    FamilySearchNoLoginSource,
    FAMILYSEARCH_COLLECTIONS,
)
from gps_agents.sources.familysearch_client import (
    FamilySearchClient,
    ClientConfig as FamilySearchClientConfig,
    Environment as FamilySearchEnvironment,
    SearchParams as FamilySearchSearchParams,
    SearchResponse as FamilySearchSearchResponse,
    Person as FamilySearchPerson,
    RecordCollection as FamilySearchCollection,
    TokenResponse as FamilySearchTokenResponse,
    quick_search as familysearch_quick_search,
)
from gps_agents.sources.findmypast import FindMyPastSource
from gps_agents.sources.fold3 import Fold3Source
from gps_agents.sources.gedcom import GedcomSource
from gps_agents.sources.jerripedia import JerripediaSource
from gps_agents.sources.myheritage import MyHeritageSource
from gps_agents.sources.rootsweb import RootsWebSource
from gps_agents.sources.router import (
    RecordType,
    Region,
    RouterConfig,
    SearchRouter,
    SourceSearchResult,
    UnifiedSearchResult,
    create_default_router,
    detect_freedmen_context,
    FREEDMEN_CONTEXT_KEYWORDS,
    INDIAN_TERRITORY_PLACES,
)
from gps_agents.sources.chronicling_america import ChroniclingAmericaSource
from gps_agents.sources.ssdi import SSDISource, SteveMorseOneStepSource
from gps_agents.sources.usgenweb import USGenWebSource
from gps_agents.sources.wikitree import (
    WikiTreeSource,
    CensusRecord as WikiTreeCensusRecord,
    US_CENSUS_YEARS,
    CENSUS_PATTERNS as WIKITREE_CENSUS_PATTERNS,
)

# New free sources
from gps_agents.sources.billiongraves import BillionGravesSource
from gps_agents.sources.freecen_uk import FreeCENSource
from gps_agents.sources.cyndislist import CyndisListSource, NorwayBMDSource, BelgiumBMDSource
from gps_agents.sources.jewishgen import JewishGenSource, YadVashemSource
from gps_agents.sources.legacy_obituaries import (
    LegacyObituariesSource,
    NewspaperObituariesSource,
)
from gps_agents.sources.afrigeneas import (
    AfricanAmericanGenealogySource,
    FreedmansBureauSource,
    SlaveSchedulesSource,
)
from gps_agents.sources.library_of_congress import (
    LibraryOfCongressSource,
    NYPLSource,
    ImmigrationRecordsSource,
)
from gps_agents.sources.california_vitals import (
    CaliforniaVitalsSource,
    CaliforniaDeathIndexSource,
    CaliforniaBirthIndexSource,
)
from gps_agents.sources.free_census import (
    FreeCensusSource,
    CensusFinderSource,
    CensusGovSource,
    CENSUS_VERIFICATION_FIELDS,
    CENSUS_RACE_CODES,
    normalize_census_race,
    compare_census_race,
)
from gps_agents.sources.sortedbyname import (
    SortedByNameSource,
    SortedByDateSource,
)
from gps_agents.sources.nara_census import (
    NARACensusSource,
    InternetArchiveCensusSource,
    LibraryAccessSource,
)
from gps_agents.sources.pasadena_news_index import (
    PasadenaNewsIndexSource,
    LosAngelesCountyNewspapersSource,
)
from gps_agents.sources.tri_valley import (
    LAGSSource,
    BunshahIndexSource,
    PleasantonWeeklySource,
    CalisphereSource,
    TriValleyGenealogySource,
)
from gps_agents.sources.gold_country import (
    ElDoradoCountySource,
    TuolumneCountySource,
    PlacerCountySource,
    MariposaCountySource,
    NevadaCountySource,
    GoldCountrySource,
)
from gps_agents.sources.ventura_county import (
    VenturaCountyGenealogySource,
    OxnardLibrarySource,
    MuseumOfVenturaCountySource,
    VenturaCountySource,
)
from gps_agents.sources.altadena_la_county import (
    AltadenaHistoricalSocietySource,
    LAPLGenealogySource,
    HuntingtonLibrarySource,
    USCDigitalLibrarySource,
    LosAngelesCountySource,
)
from gps_agents.sources.oklahoma import (
    OklahomaHistoricalSocietySource,
    OklahomaVitalRecordsSource,
    OklahomaNativeAmericanSource,
    OklahomaGenealogySource,
    OHSDawesRollsSource,
    DAWES_TRIBAL_NATIONS,
    parse_cross_references,
)
from gps_agents.sources.north_carolina import (
    NCStateArchivesSource,
    NCVitalRecordsSource,
    NCAfricanAmericanSource,
    NCCountyRecordsSource,
    NorthCarolinaGenealogySource,
)
from gps_agents.sources.headless import (
    HeadlessBrowser,
    HeadlessConfig,
    SearchResult as HeadlessSearchResult,
    run_headless_search,
    search_sync as headless_search_sync,
)

# International sources - Ireland
from gps_agents.sources.ireland import (
    IrishGenealogySource,
    RootsIrelandSource,
    GRONISource,
    IrishGenealogyAggregateSource,
    IRISH_COUNTIES,
)

# International sources - Germany
from gps_agents.sources.germany import (
    ArchionSource,
    MatriculaSource,
    GenealogyNetSource,
    FamilienkundeSource,
    GermanGenealogyAggregateSource,
    GERMAN_NAME_SUBSTITUTIONS,
    GERMAN_STATES,
)

# International sources - Scandinavia
from gps_agents.sources.scandinavia import (
    DigitalarkivetSource,
    ArkivDigitalSource,
    DanishArchivesSource,
    FinnishArchivesSource,
    IcelandicArchivesSource,
    ScandinavianGenealogyAggregateSource,
    SWEDISH_CENSUS_YEARS,
    NORWEGIAN_CENSUS_YEARS,
    DANISH_CENSUS_YEARS,
    SCANDINAVIAN_PATRONYMICS,
)

# FreeBMD (UK)
from gps_agents.sources.freebmd import FreeBMDSource

__all__ = [
    # Sources - Original
    "AccessGenealogySource",
    "ChroniclingAmericaSource",
    "FamilySearchSource",
    "FamilySearchNoLoginSource",
    "FAMILYSEARCH_COLLECTIONS",
    # FamilySearch Client (modern API)
    "FamilySearchClient",
    "FamilySearchClientConfig",
    "FamilySearchEnvironment",
    "FamilySearchSearchParams",
    "FamilySearchSearchResponse",
    "FamilySearchPerson",
    "FamilySearchCollection",
    "FamilySearchTokenResponse",
    "familysearch_quick_search",
    "FindMyPastSource",
    "Fold3Source",
    "GedcomSource",
    "JerripediaSource",
    "MyHeritageSource",
    "RootsWebSource",
    "SSDISource",
    "SteveMorseOneStepSource",
    "USGenWebSource",
    "WikiTreeSource",
    # WikiTree Census utilities
    "WikiTreeCensusRecord",
    "US_CENSUS_YEARS",
    "WIKITREE_CENSUS_PATTERNS",
    # Sources - Cemetery/Burial
    "BillionGravesSource",
    # Sources - UK Census
    "FreeCENSource",
    # Sources - Resource Directories
    "CyndisListSource",
    "NorwayBMDSource",
    "BelgiumBMDSource",
    # Sources - Jewish Genealogy
    "JewishGenSource",
    "YadVashemSource",
    # Sources - Obituaries
    "LegacyObituariesSource",
    "NewspaperObituariesSource",
    # Sources - African American Genealogy
    "AfricanAmericanGenealogySource",
    "FreedmansBureauSource",
    "SlaveSchedulesSource",
    # Sources - Libraries and Archives
    "LibraryOfCongressSource",
    "NYPLSource",
    "ImmigrationRecordsSource",
    # Sources - Vital Records
    "CaliforniaVitalsSource",
    "CaliforniaDeathIndexSource",
    "CaliforniaBirthIndexSource",
    # Sources - Free Census
    "FreeCensusSource",
    "CensusFinderSource",
    "CensusGovSource",
    # Census utilities
    "CENSUS_VERIFICATION_FIELDS",
    "CENSUS_RACE_CODES",
    "normalize_census_race",
    "compare_census_race",
    # GEDCOM/Name Index Sources
    "SortedByNameSource",
    "SortedByDateSource",
    # NARA/Archives/Library Sources
    "NARACensusSource",
    "InternetArchiveCensusSource",
    "LibraryAccessSource",
    # Sources - Local Newspapers (California)
    "PasadenaNewsIndexSource",
    "LosAngelesCountyNewspapersSource",
    # Sources - Tri-Valley (Livermore, Pleasanton, Dublin)
    "LAGSSource",
    "BunshahIndexSource",
    "PleasantonWeeklySource",
    "CalisphereSource",
    "TriValleyGenealogySource",
    # Sources - Gold Country (Highway 49 Corridor)
    "ElDoradoCountySource",
    "TuolumneCountySource",
    "PlacerCountySource",
    "MariposaCountySource",
    "NevadaCountySource",
    "GoldCountrySource",
    # Sources - Ventura County (Ventura, Oxnard, Camarillo)
    "VenturaCountyGenealogySource",
    "OxnardLibrarySource",
    "MuseumOfVenturaCountySource",
    "VenturaCountySource",
    # Sources - Los Angeles County (Altadena, Pasadena, LA)
    "AltadenaHistoricalSocietySource",
    "LAPLGenealogySource",
    "HuntingtonLibrarySource",
    "USCDigitalLibrarySource",
    "LosAngelesCountySource",
    # Sources - Oklahoma (with Native American records)
    "OklahomaHistoricalSocietySource",
    "OklahomaVitalRecordsSource",
    "OklahomaNativeAmericanSource",
    "OklahomaGenealogySource",
    "OHSDawesRollsSource",
    "DAWES_TRIBAL_NATIONS",
    "parse_cross_references",
    # Sources - North Carolina (Wake/Durham Counties)
    "NCStateArchivesSource",
    "NCVitalRecordsSource",
    "NCAfricanAmericanSource",
    "NCCountyRecordsSource",
    "NorthCarolinaGenealogySource",
    # Headless browser utilities
    "HeadlessBrowser",
    "HeadlessConfig",
    "HeadlessSearchResult",
    "run_headless_search",
    "headless_search_sync",
    # Base classes
    "BaseSource",
    "GenealogySource",
    # Models
    "RawRecord",
    "SearchQuery",
    # Router
    "RecordType",
    "Region",
    "RouterConfig",
    "SearchRouter",
    "SourceSearchResult",
    "UnifiedSearchResult",
    "create_default_router",
    # Freedmen/tribal detection
    "detect_freedmen_context",
    "FREEDMEN_CONTEXT_KEYWORDS",
    "INDIAN_TERRITORY_PLACES",
    # International Sources - Ireland
    "IrishGenealogySource",
    "RootsIrelandSource",
    "GRONISource",
    "IrishGenealogyAggregateSource",
    "IRISH_COUNTIES",
    # International Sources - Germany
    "ArchionSource",
    "MatriculaSource",
    "GenealogyNetSource",
    "FamilienkundeSource",
    "GermanGenealogyAggregateSource",
    "GERMAN_NAME_SUBSTITUTIONS",
    "GERMAN_STATES",
    # International Sources - Scandinavia
    "DigitalarkivetSource",
    "ArkivDigitalSource",
    "DanishArchivesSource",
    "FinnishArchivesSource",
    "IcelandicArchivesSource",
    "ScandinavianGenealogyAggregateSource",
    "SWEDISH_CENSUS_YEARS",
    "NORWEGIAN_CENSUS_YEARS",
    "DANISH_CENSUS_YEARS",
    "SCANDINAVIAN_PATRONYMICS",
    # UK Sources
    "FreeBMDSource",
]
