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
)
from gps_agents.sources.chronicling_america import ChroniclingAmericaSource
from gps_agents.sources.ssdi import SSDISource, SteveMorseOneStepSource
from gps_agents.sources.usgenweb import USGenWebSource
from gps_agents.sources.wikitree import WikiTreeSource

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

__all__ = [
    # Sources - Original
    "AccessGenealogySource",
    "ChroniclingAmericaSource",
    "FamilySearchSource",
    "FamilySearchNoLoginSource",
    "FAMILYSEARCH_COLLECTIONS",
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
]
