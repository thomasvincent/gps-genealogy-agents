"""Gramps data models for genealogy research.

These models represent genealogical entities compatible with Gramps
and GEDCOM standards, optimized for GPS-compliant research.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GrampsDate(BaseModel):
    """Genealogical date with uncertainty handling."""
    year: int | None = None
    month: int | None = None
    day: int | None = None
    approximate: bool = False
    before: bool = False
    after: bool = False
    range_end: GrampsDate | None = None
    text: str | None = None  # Original text representation

    def __str__(self) -> str:
        if self.text:
            return self.text
        parts = []
        if self.before:
            parts.append("BEF")
        elif self.after:
            parts.append("AFT")
        elif self.approximate:
            parts.append("ABT")

        if self.day:
            parts.append(str(self.day))
        if self.month:
            parts.append(str(self.month))
        if self.year:
            parts.append(str(self.year))

        return " ".join(parts) or "Unknown"


class Place(BaseModel):
    """Geographic location."""
    name: str = ""
    city: str | None = None
    county: str | None = None
    state: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    gramps_id: str | None = None

    def __str__(self) -> str:
        parts = [p for p in [self.city, self.county, self.state, self.country] if p]
        return ", ".join(parts) or self.name


class Name(BaseModel):
    """Person name with components."""
    given: str = ""
    surname: str = ""
    suffix: str | None = None
    prefix: str | None = None
    nickname: str | None = None
    name_type: str = "birth"  # birth, married, alias

    @property
    def full_name(self) -> str:
        parts = []
        if self.prefix:
            parts.append(self.prefix)
        if self.given:
            parts.append(self.given)
        if self.surname:
            parts.append(self.surname)
        if self.suffix:
            parts.append(self.suffix)
        return " ".join(parts)


class EventType(str, Enum):
    """Types of life events."""
    BIRTH = "birth"
    DEATH = "death"
    BURIAL = "burial"
    BAPTISM = "baptism"
    CHRISTENING = "christening"
    MARRIAGE = "marriage"
    DIVORCE = "divorce"
    CENSUS = "census"
    IMMIGRATION = "immigration"
    EMIGRATION = "emigration"
    NATURALIZATION = "naturalization"
    RESIDENCE = "residence"
    OCCUPATION = "occupation"
    MILITARY = "military"
    EDUCATION = "education"
    OTHER = "other"


class Event(BaseModel):
    """Life event."""
    event_type: EventType = EventType.OTHER
    date: GrampsDate | None = None
    place: Place | None = None
    description: str | None = None
    gramps_id: str | None = None
    citations: list[str] = Field(default_factory=list)


class Person(BaseModel):
    """Individual in the family tree."""
    gramps_id: str | None = None
    names: list[Name] = Field(default_factory=list)
    sex: str = "U"  # M, F, U
    birth: Event | None = None
    death: Event | None = None
    events: list[Event] = Field(default_factory=list)
    parent_family_ids: list[str] = Field(default_factory=list)
    family_ids: list[str] = Field(default_factory=list)
    note: str | None = None
    is_private: bool = False

    @property
    def primary_name(self) -> Name | None:
        return self.names[0] if self.names else None

    @property
    def display_name(self) -> str:
        if self.primary_name:
            return self.primary_name.full_name
        return "Unknown"


class Family(BaseModel):
    """Family unit linking individuals."""
    gramps_id: str | None = None
    husband_id: str | None = None
    wife_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    marriage: Event | None = None
    events: list[Event] = Field(default_factory=list)
    note: str | None = None


class SourceLevel(str, Enum):
    """Evidence Explained source classification."""
    ORIGINAL = "original"
    DERIVATIVE = "derivative"
    AUTHORED = "authored"


class Source(BaseModel):
    """Source of genealogical information."""
    gramps_id: str | None = None
    title: str = ""
    author: str | None = None
    publisher: str | None = None
    publication_info: str | None = None
    repository: str | None = None
    level: SourceLevel = SourceLevel.DERIVATIVE
    url: str | None = None
    note: str | None = None


class Citation(BaseModel):
    """Citation linking facts to sources."""
    gramps_id: str | None = None
    source_id: str = ""
    page: str | None = None  # Specific location within source
    date: GrampsDate | None = None
    confidence: int = 2  # 0-4, Gramps confidence scale
    note: str | None = None


class Repository(BaseModel):
    """Archive or repository holding sources."""
    gramps_id: str | None = None
    name: str = ""
    address: str | None = None
    url: str | None = None
    repository_type: str = "library"
