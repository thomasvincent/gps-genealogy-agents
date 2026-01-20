"""Data source connectors and smart router for genealogy research."""
from __future__ import annotations

from gps_agents.models.search import RawRecord, SearchQuery
from gps_agents.sources.accessgenealogy import AccessGenealogySource
from gps_agents.sources.base import BaseSource, GenealogySource
from gps_agents.sources.familysearch import FamilySearchSource
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

__all__ = [
    # Sources
    "AccessGenealogySource",
    "ChroniclingAmericaSource",
    "FamilySearchSource",
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
