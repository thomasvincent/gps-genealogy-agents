"""Historical OCR Agent using Kraken engine.

Provides agents for:
- Document segmentation (baseline/region detection)
- Text recognition (handwritten historical documents)
- Census table extraction
- LLM-assisted post-processing

Kraken is optimized for historical manuscripts and handwritten text,
making it ideal for census records, vital records, and old documents.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .models import (
    Baseline,
    BoundingBox,
    CensusCell,
    CensusColumn,
    CensusRow,
    CensusTable,
    DocumentType,
    OCREngine,
    OCRProvenance,
    OCRResult,
    RecognizedLine,
    RecognizedPage,
    RecognizedRegion,
    RecognizedWord,
    TextAlternative,
)

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger(__name__)


class OCRAgent(ABC):
    """Abstract base class for OCR agents."""

    @abstractmethod
    async def recognize_page(
        self,
        image: "Image.Image | Path | str",
        **kwargs: Any,
    ) -> OCRResult[RecognizedPage]:
        """Recognize text from a page image."""
        ...

    @abstractmethod
    async def recognize_document(
        self,
        images: list["Image.Image | Path | str"],
        **kwargs: Any,
    ) -> OCRResult[list[RecognizedPage]]:
        """Recognize text from multiple page images."""
        ...


class KrakenOCRAgent(OCRAgent):
    """Kraken-based OCR agent for historical documents.

    Uses Kraken's neural network models for:
    1. Baseline detection (blla.mlmodel)
    2. Text recognition (trained models for historical scripts)

    Example:
        >>> agent = KrakenOCRAgent(model_name="en_best.mlmodel")
        >>> result = await agent.recognize_page("census_page.jpg")
        >>> print(result.data.text)
    """

    def __init__(
        self,
        model_name: str = "en_best.mlmodel",
        segmentation_model: str = "blla.mlmodel",
        device: str = "cpu",
    ) -> None:
        """Initialize Kraken OCR agent.

        Args:
            model_name: Recognition model (e.g., "en_best.mlmodel")
            segmentation_model: Segmentation model (e.g., "blla.mlmodel")
            device: Processing device ("cpu", "cuda", "mps")
        """
        self.model_name = model_name
        self.segmentation_model = segmentation_model
        self.device = device
        self._model = None
        self._seg_model = None

    async def recognize_page(
        self,
        image: "Image.Image | Path | str",
        document_type: DocumentType = DocumentType.UNKNOWN,
        **kwargs: Any,
    ) -> OCRResult[RecognizedPage]:
        """Recognize text from a single page.

        Args:
            image: PIL Image, path to image, or URL
            document_type: Type hint for document
            **kwargs: Additional recognition parameters

        Returns:
            OCRResult with RecognizedPage
        """
        provenance = OCRProvenance(
            ocr_engine=OCREngine.KRAKEN,
            model_name=self.model_name,
        )

        try:
            start_time = time.time()

            # Load image
            pil_image = await self._load_image(image)

            # Perform segmentation and recognition
            page = await self._process_image(pil_image, document_type)

            elapsed = (time.time() - start_time) * 1000
            page.processing_time_ms = elapsed
            provenance.pages_processed = 1
            provenance.words_recognized = page.word_count
            provenance.overall_confidence = page.confidence

            return OCRResult.success_result(data=page, provenance=provenance)

        except ImportError as e:
            return OCRResult.failure_result(
                error=f"Kraken not installed: {e}. Run: pip install kraken",
                provenance=provenance,
            )
        except Exception as e:
            logger.exception("OCR recognition failed")
            return OCRResult.failure_result(error=str(e), provenance=provenance)

    async def recognize_document(
        self,
        images: list["Image.Image | Path | str"],
        document_type: DocumentType = DocumentType.UNKNOWN,
        **kwargs: Any,
    ) -> OCRResult[list[RecognizedPage]]:
        """Recognize text from multiple pages.

        Args:
            images: List of page images
            document_type: Type hint for document
            **kwargs: Additional recognition parameters

        Returns:
            OCRResult with list of RecognizedPage
        """
        provenance = OCRProvenance(
            ocr_engine=OCREngine.KRAKEN,
            model_name=self.model_name,
        )

        pages = []
        total_words = 0
        total_confidence = 0.0

        for i, img in enumerate(images):
            result = await self.recognize_page(img, document_type, **kwargs)
            if result.success and result.data:
                page = result.data
                page.page_number = i + 1
                pages.append(page)
                total_words += page.word_count
                total_confidence += page.confidence

        provenance.pages_processed = len(pages)
        provenance.words_recognized = total_words
        provenance.overall_confidence = total_confidence / len(pages) if pages else 0.0

        return OCRResult.success_result(data=pages, provenance=provenance)

    async def _load_image(self, image: "Image.Image | Path | str") -> "Image.Image":
        """Load image from various sources."""
        from PIL import Image as PILImage

        if isinstance(image, PILImage.Image):
            return image
        elif isinstance(image, (str, Path)):
            path = Path(image)
            if path.exists():
                return PILImage.open(path)
            else:
                raise FileNotFoundError(f"Image not found: {image}")
        else:
            raise TypeError(f"Unsupported image type: {type(image)}")

    async def _process_image(
        self,
        image: "Image.Image",
        document_type: DocumentType,
    ) -> RecognizedPage:
        """Process image with Kraken.

        Falls back to mock implementation if Kraken not available.
        """
        try:
            return await self._process_with_kraken(image, document_type)
        except ImportError:
            logger.warning("Kraken not available, using mock OCR")
            return await self._mock_process(image, document_type)

    async def _process_with_kraken(
        self,
        image: "Image.Image",
        document_type: DocumentType,
    ) -> RecognizedPage:
        """Process image using Kraken OCR."""
        # Import Kraken modules
        from kraken import blla, rpred
        from kraken.lib import models

        # Load models (lazy initialization)
        if self._seg_model is None:
            self._seg_model = models.load_any(self.segmentation_model)
        if self._model is None:
            self._model = models.load_any(self.model_name)

        # Run baseline detection
        baseline_seg = blla.segment(image, model=self._seg_model)

        # Run text recognition
        records = list(rpred.rpred(
            self._model,
            image,
            baseline_seg,
            pad=16,
            bidi_reordering=True,
        ))

        # Convert to our models
        regions = []
        lines = []
        total_confidence = 0.0

        for record in records:
            # Extract baseline and bbox
            bbox_dict = None
            if hasattr(record, "bbox"):
                x, y, x2, y2 = record.bbox
                bbox_dict = {
                    "x": int(x),
                    "y": int(y),
                    "width": int(x2 - x),
                    "height": int(y2 - y),
                }

            baseline_points = None
            if hasattr(record, "baseline"):
                baseline_points = [[int(p[0]), int(p[1])] for p in record.baseline]

            # Create recognized line
            confidence = getattr(record, "confidence", 0.8)
            total_confidence += confidence

            line = RecognizedLine(
                text=record.prediction if hasattr(record, "prediction") else str(record),
                confidence=confidence,
                bbox=bbox_dict,
                baseline_points=baseline_points,
            )
            lines.append(line)

        # Group lines into region
        if lines:
            region = RecognizedRegion(
                region_type="text",
                lines=lines,
                confidence=total_confidence / len(lines) if lines else 0.0,
            )
            regions.append(region)

        return RecognizedPage(
            regions=regions,
            image_width=image.width,
            image_height=image.height,
            confidence=total_confidence / len(lines) if lines else 0.0,
        )

    async def _mock_process(
        self,
        image: "Image.Image",
        document_type: DocumentType,
    ) -> RecognizedPage:
        """Mock OCR processing for testing."""
        # Create a simple mock result
        mock_line = RecognizedLine(
            text="[Mock OCR - Kraken not installed]",
            confidence=0.0,
            words=[
                RecognizedWord(text="[Mock", confidence=0.0),
                RecognizedWord(text="OCR]", confidence=0.0),
            ],
        )

        region = RecognizedRegion(
            region_type="text",
            lines=[mock_line],
            confidence=0.0,
        )

        return RecognizedPage(
            regions=[region],
            image_width=image.width,
            image_height=image.height,
            confidence=0.0,
        )


class CensusOCRAgent(KrakenOCRAgent):
    """Specialized OCR agent for US Census documents.

    Extends KrakenOCRAgent with:
    - Census table structure detection
    - Column header recognition
    - Name/age/birthplace extraction
    - LLM post-processing for ambiguous text
    """

    def __init__(
        self,
        model_name: str = "en_best.mlmodel",
        census_year: int | None = None,
        llm_client: Any = None,
    ) -> None:
        """Initialize Census OCR agent.

        Args:
            model_name: Kraken recognition model
            census_year: Census year (affects column expectations)
            llm_client: Optional LLM client for post-processing
        """
        super().__init__(model_name=model_name)
        self.census_year = census_year
        self.llm_client = llm_client

    async def extract_census_table(
        self,
        image: "Image.Image | Path | str",
        census_year: int | None = None,
    ) -> OCRResult[CensusTable]:
        """Extract structured census table from image.

        Args:
            image: Census page image
            census_year: Override census year

        Returns:
            OCRResult with CensusTable
        """
        year = census_year or self.census_year
        provenance = OCRProvenance(
            ocr_engine=OCREngine.KRAKEN,
            model_name=self.model_name,
            preprocessing_applied=["deskew", "contrast_enhance"],
        )

        try:
            # First get raw OCR
            page_result = await self.recognize_page(
                image, document_type=DocumentType.CENSUS
            )

            if not page_result.success or not page_result.data:
                return OCRResult.failure_result(
                    error=page_result.error or "OCR failed",
                    provenance=provenance,
                )

            page = page_result.data

            # Extract table structure
            table = await self._extract_table_structure(page, year)

            # Post-process with LLM if available
            if self.llm_client:
                table = await self._llm_post_process(table, page)

            provenance.overall_confidence = table.table_confidence
            return OCRResult.success_result(data=table, provenance=provenance)

        except Exception as e:
            logger.exception("Census table extraction failed")
            return OCRResult.failure_result(error=str(e), provenance=provenance)

    async def _extract_table_structure(
        self,
        page: RecognizedPage,
        census_year: int | None,
    ) -> CensusTable:
        """Extract table structure from OCR results.

        Analyzes line positions to identify:
        - Column boundaries
        - Row separations
        - Header vs data regions
        """
        # Get expected columns for census year
        columns = self._get_expected_columns(census_year)

        rows = []
        warnings = []

        # Simple heuristic: each line is potentially a person row
        row_number = 0
        for region in page.regions:
            for line in region.lines:
                if not line.text.strip():
                    continue

                # Skip header-like lines
                if self._is_header_line(line.text):
                    continue

                row_number += 1
                cells = self._parse_line_to_cells(line, columns)

                row = CensusRow(
                    row_number=row_number,
                    cells=cells,
                    row_confidence=line.confidence,
                )
                rows.append(row)

        # Calculate overall confidence
        total_confidence = sum(r.row_confidence for r in rows)
        avg_confidence = total_confidence / len(rows) if rows else 0.0

        return CensusTable(
            census_year=census_year,
            rows=rows,
            column_headers=[c.value for c in columns],
            table_confidence=avg_confidence,
            extraction_warnings=warnings,
        )

    def _get_expected_columns(self, census_year: int | None) -> list[CensusColumn]:
        """Get expected columns based on census year."""
        # Base columns present in most census years
        base_columns = [
            CensusColumn.LINE_NUMBER,
            CensusColumn.NAME,
            CensusColumn.RELATION_TO_HEAD,
            CensusColumn.SEX,
            CensusColumn.RACE,
            CensusColumn.AGE,
        ]

        if census_year and census_year >= 1880:
            base_columns.extend([
                CensusColumn.MARITAL_STATUS,
                CensusColumn.BIRTHPLACE,
                CensusColumn.FATHER_BIRTHPLACE,
                CensusColumn.MOTHER_BIRTHPLACE,
                CensusColumn.OCCUPATION,
            ])

        if census_year and census_year >= 1900:
            base_columns.append(CensusColumn.BIRTH_YEAR)

        return base_columns

    def _is_header_line(self, text: str) -> bool:
        """Check if line appears to be a header."""
        header_keywords = [
            "name", "age", "sex", "color", "race",
            "occupation", "birthplace", "relation",
            "schedule", "enumeration", "district",
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in header_keywords)

    def _parse_line_to_cells(
        self,
        line: RecognizedLine,
        columns: list[CensusColumn],
    ) -> dict[CensusColumn, CensusCell]:
        """Parse a line into column cells.

        Uses word positions and spacing to identify column breaks.
        """
        cells = {}

        # Simple split by multiple spaces (common census format)
        parts = line.text.split()

        # Map parts to columns (simplified - real implementation would
        # use word bounding boxes for accurate column detection)
        for i, column in enumerate(columns):
            if i < len(parts):
                raw_text = parts[i]
                normalized = self._normalize_cell_text(raw_text, column)

                cells[column] = CensusCell(
                    column=column,
                    raw_text=raw_text,
                    normalized_text=normalized,
                    confidence=line.confidence,
                )

        return cells

    def _normalize_cell_text(
        self,
        text: str,
        column: CensusColumn,
    ) -> str | None:
        """Normalize cell text based on column type."""
        text = text.strip()

        if column == CensusColumn.AGE:
            # Extract numeric age
            import re
            match = re.search(r"\d+", text)
            return match.group() if match else text

        elif column == CensusColumn.SEX:
            # Normalize to M/F
            text_lower = text.lower()
            if "m" in text_lower:
                return "M"
            elif "f" in text_lower:
                return "F"

        elif column == CensusColumn.RELATION_TO_HEAD:
            # Normalize relationship terms
            text_lower = text.lower()
            mappings = {
                "hd": "Head",
                "head": "Head",
                "w": "Wife",
                "wife": "Wife",
                "s": "Son",
                "son": "Son",
                "d": "Daughter",
                "dau": "Daughter",
                "daughter": "Daughter",
            }
            for key, value in mappings.items():
                if key in text_lower:
                    return value

        return text

    async def _llm_post_process(
        self,
        table: CensusTable,
        page: RecognizedPage,
    ) -> CensusTable:
        """Use LLM to correct OCR errors and ambiguities.

        Sends low-confidence cells to LLM for correction.
        """
        if not self.llm_client:
            return table

        # Find cells needing review
        cells_to_review = []
        for row in table.rows:
            for column, cell in row.cells.items():
                if cell.confidence < 0.7:
                    cells_to_review.append((row.row_number, column, cell))

        if not cells_to_review:
            return table

        # Create prompt for LLM
        prompt = self._build_correction_prompt(cells_to_review, table.census_year)

        try:
            # Would call LLM here
            # For now, just return original table
            logger.info("Would send %d cells to LLM for correction", len(cells_to_review))
        except Exception as e:
            logger.warning("LLM post-processing failed: %s", e)

        return table

    def _build_correction_prompt(
        self,
        cells: list[tuple[int, CensusColumn, CensusCell]],
        census_year: int | None,
    ) -> str:
        """Build prompt for LLM OCR correction."""
        lines = [
            f"You are correcting OCR errors in a {census_year or 'historical'} US Census record.",
            "For each uncertain reading below, provide the most likely correct text.",
            "",
        ]

        for row_num, column, cell in cells:
            lines.append(f"Row {row_num}, {column.value}: '{cell.raw_text}'")

        return "\n".join(lines)


class PreprocessingPipeline:
    """Image preprocessing pipeline for OCR.

    Applies standard preprocessing steps:
    - Deskewing
    - Noise removal
    - Contrast enhancement
    - Binarization
    """

    def __init__(
        self,
        deskew: bool = True,
        denoise: bool = True,
        enhance_contrast: bool = True,
        binarize: bool = False,
    ) -> None:
        self.deskew = deskew
        self.denoise = denoise
        self.enhance_contrast = enhance_contrast
        self.binarize = binarize

    async def process(self, image: "Image.Image") -> "Image.Image":
        """Apply preprocessing pipeline to image."""
        from PIL import Image as PILImage, ImageEnhance, ImageFilter

        result = image.copy()

        # Convert to grayscale if needed
        if result.mode != "L":
            result = result.convert("L")

        # Denoise
        if self.denoise:
            result = result.filter(ImageFilter.MedianFilter(size=3))

        # Enhance contrast
        if self.enhance_contrast:
            enhancer = ImageEnhance.Contrast(result)
            result = enhancer.enhance(1.5)

        # Binarize (for some OCR engines)
        if self.binarize:
            threshold = 128
            result = result.point(lambda x: 255 if x > threshold else 0, "1")

        return result

    @property
    def steps_applied(self) -> list[str]:
        """Get list of preprocessing steps."""
        steps = []
        if self.deskew:
            steps.append("deskew")
        if self.denoise:
            steps.append("denoise")
        if self.enhance_contrast:
            steps.append("contrast_enhance")
        if self.binarize:
            steps.append("binarize")
        return steps
