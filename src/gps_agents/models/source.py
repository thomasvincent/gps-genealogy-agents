"""Source citation models."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    """Type of evidence provided by a source."""

    DIRECT = "direct"  # Source directly states the fact
    INDIRECT = "indirect"  # Fact must be inferred from source
    NEGATIVE = "negative"  # Absence of expected record is evidence


class SourceCitation(BaseModel):
    """A citation to a genealogical source."""

    repository: str = Field(description="Source repository (e.g., 'FamilySearch', 'WikiTree')")
    record_id: str = Field(description="Unique identifier within the repository")
    url: str | None = Field(default=None, description="Direct URL to the record if available")
    accessed_at: datetime = Field(default_factory=datetime.utcnow)
    evidence_type: EvidenceType = Field(default=EvidenceType.DIRECT)
    record_type: str | None = Field(
        default=None, description="Type of record (e.g., 'birth certificate', 'census')"
    )
    original_text: str | None = Field(
        default=None, description="Verbatim text from the original record"
    )
    informant: str | None = Field(
        default=None, description="Who provided the information (if known)"
    )
    informant_relationship: str | None = Field(
        default=None, description="Informant's relationship to the subject"
    )

    def to_evidence_explained(self) -> str:
        """Format citation according to Evidence Explained standards."""
        parts = [self.repository]
        if self.record_type:
            parts.append(f'"{self.record_type}"')
        parts.append(f"record {self.record_id}")
        if self.url:
            parts.append(f"({self.url})")
        parts.append(f"accessed {self.accessed_at.strftime('%d %B %Y')}")
        return ", ".join(parts) + "."
