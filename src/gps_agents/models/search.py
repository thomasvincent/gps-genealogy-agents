"""Search query and raw record models."""

from datetime import datetime

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Query for searching genealogical sources."""

    given_name: str | None = Field(default=None)
    surname: str | None = Field(default=None)
    surname_variants: list[str] = Field(
        default_factory=list, description="Soundex, historical spellings, etc."
    )
    birth_year: int | None = Field(default=None)
    birth_year_range: int = Field(default=5, description="± years to search")
    birth_place: str | None = Field(default=None)
    death_year: int | None = Field(default=None)
    death_year_range: int = Field(default=5)
    death_place: str | None = Field(default=None)
    residence: str | None = Field(default=None)
    spouse_name: str | None = Field(default=None)
    father_name: str | None = Field(default=None)
    mother_name: str | None = Field(default=None)
    record_types: list[str] = Field(
        default_factory=list,
        description="Types to search: birth, death, marriage, census, military, etc.",
    )
    exclude_sources: list[str] = Field(
        default_factory=list, description="Source repositories to skip"
    )

    def get_year_range(self, year: int | None, range_val: int) -> tuple[int, int] | None:
        """Get min/max year range for searching."""
        if year is None:
            return None
        return (year - range_val, year + range_val)


class RawRecord(BaseModel):
    """Raw record returned from a data source before processing."""

    source: str = Field(description="Which source returned this record")
    record_id: str = Field(description="ID within the source")
    record_type: str = Field(description="Type of record")
    url: str | None = Field(default=None)
    raw_data: dict = Field(default_factory=dict, description="Original response data")
    extracted_fields: dict[str, str | None] = Field(
        default_factory=dict, description="Parsed fields from the record"
    )
    accessed_at: datetime = Field(default_factory=datetime.utcnow)
    confidence_hint: float | None = Field(
        default=None, description="Source's own confidence if provided"
    )
    needs_translation: bool = Field(default=False)
    language: str = Field(default="en")
