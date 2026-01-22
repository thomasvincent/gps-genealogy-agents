"""OCR data models for historical document recognition.

Provides Pydantic models for:
- Text recognition results (lines, regions, pages)
- Bounding box coordinates
- Confidence scores and alternatives
- Census-specific field extraction

Designed for integration with Kraken OCR engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field


class OCREngine(str, Enum):
    """Supported OCR engines."""
    KRAKEN = "kraken"
    TESSERACT = "tesseract"
    GOOGLE_VISION = "google_vision"
    AWS_TEXTRACT = "aws_textract"


class DocumentType(str, Enum):
    """Types of historical documents."""
    CENSUS = "census"
    BIRTH_CERTIFICATE = "birth_certificate"
    DEATH_CERTIFICATE = "death_certificate"
    MARRIAGE_CERTIFICATE = "marriage_certificate"
    MILITARY_RECORD = "military_record"
    IMMIGRATION_RECORD = "immigration_record"
    NEWSPAPER = "newspaper"
    HANDWRITTEN_LETTER = "handwritten_letter"
    UNKNOWN = "unknown"


class RecognitionConfidence(str, Enum):
    """Confidence levels for OCR recognition."""
    HIGH = "high"  # > 0.9
    MEDIUM = "medium"  # 0.7-0.9
    LOW = "low"  # 0.5-0.7
    VERY_LOW = "very_low"  # < 0.5


@dataclass
class BoundingBox:
    """Bounding box coordinates for a recognized region.

    Coordinates are in pixels from top-left origin.
    """
    x: int  # Left edge
    y: int  # Top edge
    width: int
    height: int

    @property
    def right(self) -> int:
        """Right edge x-coordinate."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """Bottom edge y-coordinate."""
        return self.y + self.height

    @property
    def center(self) -> tuple[int, int]:
        """Center point (x, y)."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def area(self) -> int:
        """Area in pixels."""
        return self.width * self.height

    def overlaps(self, other: BoundingBox) -> bool:
        """Check if this box overlaps with another."""
        return not (
            self.right < other.x or
            other.right < self.x or
            self.bottom < other.y or
            other.bottom < self.y
        )

    def intersection_over_union(self, other: BoundingBox) -> float:
        """Calculate IoU with another box."""
        if not self.overlaps(other):
            return 0.0

        inter_x = max(self.x, other.x)
        inter_y = max(self.y, other.y)
        inter_right = min(self.right, other.right)
        inter_bottom = min(self.bottom, other.bottom)

        inter_area = (inter_right - inter_x) * (inter_bottom - inter_y)
        union_area = self.area + other.area - inter_area

        return inter_area / union_area if union_area > 0 else 0.0

    def to_dict(self) -> dict[str, int]:
        """Serialize to dictionary."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class Baseline:
    """Baseline coordinates for text line detection.

    Kraken uses baselines for text alignment in handwritten documents.
    """
    points: list[tuple[int, int]]  # List of (x, y) points

    @property
    def start(self) -> tuple[int, int]:
        """Starting point of baseline."""
        return self.points[0] if self.points else (0, 0)

    @property
    def end(self) -> tuple[int, int]:
        """Ending point of baseline."""
        return self.points[-1] if self.points else (0, 0)

    @property
    def length(self) -> float:
        """Approximate length of baseline."""
        if len(self.points) < 2:
            return 0.0

        import math
        total = 0.0
        for i in range(len(self.points) - 1):
            dx = self.points[i + 1][0] - self.points[i][0]
            dy = self.points[i + 1][1] - self.points[i][1]
            total += math.sqrt(dx * dx + dy * dy)
        return total


class TextAlternative(BaseModel):
    """Alternative reading for ambiguous text."""
    text: str
    confidence: float = Field(ge=0.0, le=1.0)


class RecognizedChar(BaseModel):
    """Single recognized character with alternatives."""
    char: str
    confidence: float = Field(ge=0.0, le=1.0)
    alternatives: list[TextAlternative] = Field(default_factory=list)
    bbox: dict[str, int] | None = None


class RecognizedWord(BaseModel):
    """Recognized word with confidence and alternatives."""
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    alternatives: list[TextAlternative] = Field(default_factory=list)
    characters: list[RecognizedChar] = Field(default_factory=list)
    bbox: dict[str, int] | None = None

    @computed_field
    @property
    def confidence_level(self) -> RecognitionConfidence:
        """Get confidence level category."""
        if self.confidence > 0.9:
            return RecognitionConfidence.HIGH
        elif self.confidence > 0.7:
            return RecognitionConfidence.MEDIUM
        elif self.confidence > 0.5:
            return RecognitionConfidence.LOW
        return RecognitionConfidence.VERY_LOW

    @computed_field
    @property
    def needs_review(self) -> bool:
        """Check if word needs human review."""
        return self.confidence < 0.7


class RecognizedLine(BaseModel):
    """Single line of recognized text."""
    line_id: UUID = Field(default_factory=uuid4)
    text: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    words: list[RecognizedWord] = Field(default_factory=list)
    bbox: dict[str, int] | None = None
    baseline_points: list[list[int]] | None = None  # [[x, y], ...]

    @computed_field
    @property
    def word_count(self) -> int:
        """Number of words in line."""
        return len(self.words) if self.words else len(self.text.split())

    @computed_field
    @property
    def average_word_confidence(self) -> float:
        """Average confidence across words."""
        if not self.words:
            return self.confidence
        return sum(w.confidence for w in self.words) / len(self.words)


class RecognizedRegion(BaseModel):
    """Recognized region (block) of text."""
    region_id: UUID = Field(default_factory=uuid4)
    region_type: str = "text"  # "text", "table", "figure", "header"
    lines: list[RecognizedLine] = Field(default_factory=list)
    bbox: dict[str, int] | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    @computed_field
    @property
    def text(self) -> str:
        """Full text of region."""
        return "\n".join(line.text for line in self.lines)

    @computed_field
    @property
    def line_count(self) -> int:
        """Number of lines in region."""
        return len(self.lines)


class RecognizedPage(BaseModel):
    """Single page OCR results."""
    page_id: UUID = Field(default_factory=uuid4)
    page_number: int = 1
    regions: list[RecognizedRegion] = Field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    dpi: int = 300
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # Metadata
    source_file: str | None = None
    processing_time_ms: float = 0.0

    @computed_field
    @property
    def text(self) -> str:
        """Full text of page."""
        return "\n\n".join(region.text for region in self.regions)

    @computed_field
    @property
    def line_count(self) -> int:
        """Total lines on page."""
        return sum(r.line_count for r in self.regions)

    @computed_field
    @property
    def word_count(self) -> int:
        """Total words on page."""
        return sum(
            line.word_count
            for region in self.regions
            for line in region.lines
        )


class OCRProvenance(BaseModel):
    """Provenance tracking for OCR processing."""
    ocr_engine: OCREngine
    engine_version: str | None = None
    model_name: str | None = None
    processing_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Processing parameters
    preprocessing_applied: list[str] = Field(default_factory=list)
    language_hints: list[str] = Field(default_factory=list)

    # Quality metrics
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    pages_processed: int = 0
    characters_recognized: int = 0
    words_recognized: int = 0


T = TypeVar("T")


class OCRResult(BaseModel, Generic[T]):
    """Generic OCR result wrapper with provenance."""
    success: bool
    data: T | None = None
    provenance: OCRProvenance
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def success_result(
        cls,
        data: T,
        provenance: OCRProvenance,
        warnings: list[str] | None = None,
    ) -> "OCRResult[T]":
        """Create a successful result."""
        return cls(
            success=True,
            data=data,
            provenance=provenance,
            warnings=warnings or [],
        )

    @classmethod
    def failure_result(
        cls,
        error: str,
        provenance: OCRProvenance,
    ) -> "OCRResult[T]":
        """Create a failed result."""
        return cls(
            success=False,
            error=error,
            provenance=provenance,
        )


class CensusColumn(str, Enum):
    """Standard US Census columns."""
    LINE_NUMBER = "line_number"
    NAME = "name"
    RELATION_TO_HEAD = "relation_to_head"
    SEX = "sex"
    RACE = "race"
    AGE = "age"
    MARITAL_STATUS = "marital_status"
    BIRTH_YEAR = "birth_year"
    BIRTHPLACE = "birthplace"
    FATHER_BIRTHPLACE = "father_birthplace"
    MOTHER_BIRTHPLACE = "mother_birthplace"
    OCCUPATION = "occupation"
    CAN_READ = "can_read"
    CAN_WRITE = "can_write"


class CensusCell(BaseModel):
    """Single cell in census table."""
    column: CensusColumn
    raw_text: str
    normalized_text: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    alternatives: list[TextAlternative] = Field(default_factory=list)
    bbox: dict[str, int] | None = None


class CensusRow(BaseModel):
    """Single row (person) in census table."""
    row_number: int
    cells: dict[CensusColumn, CensusCell] = Field(default_factory=dict)
    row_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    def get_cell_text(self, column: CensusColumn) -> str | None:
        """Get text for a column."""
        cell = self.cells.get(column)
        return cell.normalized_text or cell.raw_text if cell else None

    @computed_field
    @property
    def name(self) -> str | None:
        """Get person name."""
        return self.get_cell_text(CensusColumn.NAME)

    @computed_field
    @property
    def age(self) -> int | None:
        """Get person age."""
        text = self.get_cell_text(CensusColumn.AGE)
        if text:
            try:
                return int(text)
            except ValueError:
                return None
        return None


class CensusTable(BaseModel):
    """Structured census table extraction."""
    table_id: UUID = Field(default_factory=uuid4)
    census_year: int | None = None
    page_number: int = 1
    dwelling_number: int | None = None
    family_number: int | None = None

    # Header info
    state: str | None = None
    county: str | None = None
    township: str | None = None
    enumeration_district: str | None = None

    # Data rows
    rows: list[CensusRow] = Field(default_factory=list)
    column_headers: list[str] = Field(default_factory=list)

    # Quality
    table_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    extraction_warnings: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def person_count(self) -> int:
        """Number of persons in table."""
        return len(self.rows)
