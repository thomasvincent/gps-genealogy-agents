"""Gramps integration for GPS genealogy research.

Provides access to local Gramps databases and models compatible
with Gramps 5.x and 6.x.
"""

from gps_agents.gramps.client import GrampsClient
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
    # Client
    "GrampsClient",
    # Models
    "Citation",
    "Event",
    "EventType",
    "Family",
    "GrampsDate",
    "Name",
    "Person",
    "Place",
    "Repository",
    "Source",
    "SourceLevel",
]
