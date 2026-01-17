"""Data source connectors."""

from .base import GenealogySource, SearchQuery
from .familysearch import FamilySearchSource
from .wikitree import WikiTreeSource
from .findmypast import FindMyPastSource
from .myheritage import MyHeritageSource
from .accessgenealogy import AccessGenealogySource
from .jerripedia import JerripediaSource
from .gedcom import GedcomSource

__all__ = [
    "GenealogySource",
    "SearchQuery",
    "FamilySearchSource",
    "WikiTreeSource",
    "FindMyPastSource",
    "MyHeritageSource",
    "AccessGenealogySource",
    "JerripediaSource",
    "GedcomSource",
]
