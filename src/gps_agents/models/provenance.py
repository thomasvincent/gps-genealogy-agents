"""Provenance tracking models."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class ProvenanceSource(str, Enum):
    """Source of the fact creation."""

    RESEARCH_AGENT = "research_agent"
    USER_INPUT = "user_input"
    GEDCOM_IMPORT = "gedcom_import"
    API_DISCOVERY = "api_discovery"
    WEB_SCRAPING = "web_scraping"


class Provenance(BaseModel):
    """Tracks who/what created a fact and when."""

    created_by: ProvenanceSource = Field(description="What created this fact")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_id: str | None = Field(default=None, description="Specific agent instance ID")
    session_id: str | None = Field(default=None, description="Research session ID")
    query_context: str | None = Field(
        default=None, description="Original research query that led to this fact"
    )
    discovery_method: str | None = Field(
        default=None, description="How the fact was discovered (API call, search, etc.)"
    )
    raw_response: str | None = Field(
        default=None, description="Raw API/scrape response for audit trail"
    )
