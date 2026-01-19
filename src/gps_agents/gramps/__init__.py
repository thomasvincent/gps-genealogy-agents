"""Gramps integration for GPS genealogy research.

Provides access to local Gramps databases with intelligent
match-merge logic to prevent duplicate records.
"""
from __future__ import annotations

from gps_agents.gramps.client import GrampsClient
from gps_agents.gramps.merge import (
    GrampsMerger,
    MatchConfidence,
    MatchResult,
    MergeResult,
    MergeStrategy,
    PersonMatcher,
    smart_add_person,
)
from gps_agents.gramps.models import (
    Citation,
    Event,
    EventType,
    Family,
    GrampsDate,
    Name,
    Person,
    Place,
    Repository,
    Source,
    SourceLevel,
)

__all__ = [
    # Models
    "Citation",
    "Event",
    "EventType",
    "Family",
    # Client
    "GrampsClient",
    "GrampsDate",
    # Match-Merge
    "GrampsMerger",
    "MatchConfidence",
    "MatchResult",
    "MergeResult",
    "MergeStrategy",
    "Name",
    "Person",
    "PersonMatcher",
    "Place",
    "Repository",
    "Source",
    "SourceLevel",
    "smart_add_person",
]
