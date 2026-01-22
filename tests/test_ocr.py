"""Tests for Historical OCR module."""
from __future__ import annotations

from uuid import uuid4

import pytest

from gps_agents.genealogy_crawler.ocr import (
    Baseline,
    BoundingBox,
    CensusCell,
    CensusColumn,
    CensusOCRAgent,
    CensusRow,
    CensusTable,
    DocumentType,
    KrakenOCRAgent,
    OCREngine,
    OCRProvenance,
    OCRResult,
    PreprocessingPipeline,
    RecognitionConfidence,
    RecognizedLine,
    RecognizedPage,
    RecognizedRegion,
    RecognizedWord,
    TextAlternative,
)


class TestBoundingBox:
    """Tests for BoundingBox model."""

    def test_create_bbox(self):
        """Test basic creation."""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)

        assert bbox.x == 10
        assert bbox.y == 20
        assert bbox.width == 100
        assert bbox.height == 50

    def test_right_bottom(self):
        """Test right and bottom edge calculation."""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)

        assert bbox.right == 110  # 10 + 100
        assert bbox.bottom == 70  # 20 + 50

    def test_center(self):
        """Test center point calculation."""
        bbox = BoundingBox(x=0, y=0, width=100, height=50)

        assert bbox.center == (50, 25)

    def test_area(self):
        """Test area calculation."""
        bbox = BoundingBox(x=0, y=0, width=100, height=50)

        assert bbox.area == 5000

    def test_overlaps(self):
        """Test overlap detection."""
        box1 = BoundingBox(x=0, y=0, width=100, height=100)
        box2 = BoundingBox(x=50, y=50, width=100, height=100)
        box3 = BoundingBox(x=200, y=200, width=50, height=50)

        assert box1.overlaps(box2) is True
        assert box1.overlaps(box3) is False

    def test_iou(self):
        """Test Intersection over Union calculation."""
        box1 = BoundingBox(x=0, y=0, width=100, height=100)
        box2 = BoundingBox(x=0, y=0, width=100, height=100)  # Same box

        assert box1.intersection_over_union(box2) == pytest.approx(1.0)

        box3 = BoundingBox(x=50, y=0, width=100, height=100)  # 50% overlap
        iou = box1.intersection_over_union(box3)
        assert 0.3 < iou < 0.4  # ~1/3 IoU

    def test_to_dict(self):
        """Test serialization."""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)

        data = bbox.to_dict()
        assert data == {"x": 10, "y": 20, "width": 100, "height": 50}


class TestBaseline:
    """Tests for Baseline model."""

    def test_create_baseline(self):
        """Test baseline creation."""
        baseline = Baseline(points=[(0, 100), (50, 98), (100, 100)])

        assert len(baseline.points) == 3
        assert baseline.start == (0, 100)
        assert baseline.end == (100, 100)

    def test_baseline_length(self):
        """Test baseline length calculation."""
        # Straight horizontal line
        baseline = Baseline(points=[(0, 0), (100, 0)])
        assert baseline.length == pytest.approx(100.0)

        # Diagonal line (3-4-5 triangle)
        baseline = Baseline(points=[(0, 0), (30, 40)])
        assert baseline.length == pytest.approx(50.0)


class TestRecognizedWord:
    """Tests for RecognizedWord model."""

    def test_create_word(self):
        """Test word creation."""
        word = RecognizedWord(
            text="Durham",
            confidence=0.95,
        )

        assert word.text == "Durham"
        assert word.confidence == 0.95

    def test_confidence_level_high(self):
        """Test high confidence level."""
        word = RecognizedWord(text="test", confidence=0.95)
        assert word.confidence_level == RecognitionConfidence.HIGH

    def test_confidence_level_medium(self):
        """Test medium confidence level."""
        word = RecognizedWord(text="test", confidence=0.75)
        assert word.confidence_level == RecognitionConfidence.MEDIUM

    def test_confidence_level_low(self):
        """Test low confidence level."""
        word = RecognizedWord(text="test", confidence=0.55)
        assert word.confidence_level == RecognitionConfidence.LOW

    def test_confidence_level_very_low(self):
        """Test very low confidence level."""
        word = RecognizedWord(text="test", confidence=0.3)
        assert word.confidence_level == RecognitionConfidence.VERY_LOW

    def test_needs_review(self):
        """Test review flag."""
        high_conf = RecognizedWord(text="clear", confidence=0.9)
        assert high_conf.needs_review is False

        low_conf = RecognizedWord(text="unclear", confidence=0.5)
        assert low_conf.needs_review is True


class TestRecognizedLine:
    """Tests for RecognizedLine model."""

    def test_create_line(self):
        """Test line creation."""
        line = RecognizedLine(
            text="Archie Durham",
            confidence=0.85,
        )

        assert line.text == "Archie Durham"
        assert line.word_count == 2

    def test_word_count_with_words(self):
        """Test word count from word list."""
        line = RecognizedLine(
            text="Archie Durham",
            confidence=0.85,
            words=[
                RecognizedWord(text="Archie", confidence=0.9),
                RecognizedWord(text="Durham", confidence=0.8),
            ],
        )

        assert line.word_count == 2

    def test_average_word_confidence(self):
        """Test average confidence calculation."""
        line = RecognizedLine(
            text="test line",
            confidence=0.5,  # Fallback
            words=[
                RecognizedWord(text="test", confidence=0.9),
                RecognizedWord(text="line", confidence=0.7),
            ],
        )

        assert line.average_word_confidence == pytest.approx(0.8)


class TestRecognizedPage:
    """Tests for RecognizedPage model."""

    def test_create_page(self):
        """Test page creation."""
        line = RecognizedLine(text="Test line", confidence=0.9)
        region = RecognizedRegion(lines=[line], confidence=0.9)
        page = RecognizedPage(
            regions=[region],
            image_width=800,
            image_height=1200,
        )

        assert page.image_width == 800
        assert page.line_count == 1

    def test_page_text(self):
        """Test full page text extraction."""
        line1 = RecognizedLine(text="Line one", confidence=0.9)
        line2 = RecognizedLine(text="Line two", confidence=0.9)
        region = RecognizedRegion(lines=[line1, line2], confidence=0.9)
        page = RecognizedPage(regions=[region])

        assert "Line one" in page.text
        assert "Line two" in page.text


class TestOCRResult:
    """Tests for OCRResult wrapper."""

    def test_success_result(self):
        """Test successful result creation."""
        page = RecognizedPage(regions=[], image_width=100, image_height=100)
        provenance = OCRProvenance(ocr_engine=OCREngine.KRAKEN)

        result = OCRResult.success_result(data=page, provenance=provenance)

        assert result.success is True
        assert result.data is not None
        assert result.error is None

    def test_failure_result(self):
        """Test failed result creation."""
        provenance = OCRProvenance(ocr_engine=OCREngine.KRAKEN)

        result = OCRResult.failure_result(
            error="File not found",
            provenance=provenance,
        )

        assert result.success is False
        assert result.error == "File not found"
        assert result.data is None


class TestOCRProvenance:
    """Tests for OCRProvenance model."""

    def test_create_provenance(self):
        """Test provenance creation."""
        provenance = OCRProvenance(
            ocr_engine=OCREngine.KRAKEN,
            model_name="en_best.mlmodel",
            pages_processed=5,
            words_recognized=500,
            overall_confidence=0.85,
        )

        assert provenance.ocr_engine == OCREngine.KRAKEN
        assert provenance.pages_processed == 5


class TestCensusColumn:
    """Tests for CensusColumn enum."""

    def test_column_values(self):
        """Test column enum values."""
        assert CensusColumn.NAME.value == "name"
        assert CensusColumn.AGE.value == "age"
        assert CensusColumn.BIRTHPLACE.value == "birthplace"


class TestCensusCell:
    """Tests for CensusCell model."""

    def test_create_cell(self):
        """Test cell creation."""
        cell = CensusCell(
            column=CensusColumn.NAME,
            raw_text="Archie  Durham",
            normalized_text="Archie Durham",
            confidence=0.9,
        )

        assert cell.raw_text == "Archie  Durham"
        assert cell.normalized_text == "Archie Durham"


class TestCensusRow:
    """Tests for CensusRow model."""

    def test_create_row(self):
        """Test row creation."""
        cells = {
            CensusColumn.NAME: CensusCell(
                column=CensusColumn.NAME,
                raw_text="Archie Durham",
                confidence=0.9,
            ),
            CensusColumn.AGE: CensusCell(
                column=CensusColumn.AGE,
                raw_text="23",
                normalized_text="23",
                confidence=0.95,
            ),
        }

        row = CensusRow(
            row_number=1,
            cells=cells,
            row_confidence=0.92,
        )

        assert row.row_number == 1
        assert row.name == "Archie Durham"
        assert row.age == 23

    def test_get_cell_text(self):
        """Test cell text retrieval."""
        cells = {
            CensusColumn.SEX: CensusCell(
                column=CensusColumn.SEX,
                raw_text="M",
                normalized_text="M",
                confidence=0.99,
            ),
        }

        row = CensusRow(row_number=1, cells=cells)

        assert row.get_cell_text(CensusColumn.SEX) == "M"
        assert row.get_cell_text(CensusColumn.NAME) is None


class TestCensusTable:
    """Tests for CensusTable model."""

    def test_create_table(self):
        """Test table creation."""
        row1 = CensusRow(row_number=1, cells={})
        row2 = CensusRow(row_number=2, cells={})

        table = CensusTable(
            census_year=1940,
            state="North Carolina",
            county="Durham",
            rows=[row1, row2],
            table_confidence=0.88,
        )

        assert table.census_year == 1940
        assert table.person_count == 2
        assert table.state == "North Carolina"


class TestKrakenOCRAgent:
    """Tests for KrakenOCRAgent."""

    def test_create_agent(self):
        """Test agent creation."""
        agent = KrakenOCRAgent(
            model_name="en_best.mlmodel",
            segmentation_model="blla.mlmodel",
            device="cpu",
        )

        assert agent.model_name == "en_best.mlmodel"
        assert agent.device == "cpu"

    @pytest.mark.asyncio
    async def test_recognize_page_mock(self):
        """Test page recognition with mock (no Kraken installed)."""
        from PIL import Image

        # Create a simple test image
        img = Image.new("RGB", (100, 100), color="white")

        agent = KrakenOCRAgent()
        result = await agent.recognize_page(img)

        assert result.success is True
        assert result.data is not None
        assert result.provenance.ocr_engine == OCREngine.KRAKEN


class TestCensusOCRAgent:
    """Tests for CensusOCRAgent."""

    def test_create_agent(self):
        """Test census agent creation."""
        agent = CensusOCRAgent(
            model_name="en_best.mlmodel",
            census_year=1940,
        )

        assert agent.census_year == 1940

    @pytest.mark.asyncio
    async def test_extract_census_table_mock(self):
        """Test census table extraction with mock."""
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="white")

        agent = CensusOCRAgent(census_year=1940)
        result = await agent.extract_census_table(img)

        assert result.success is True
        assert result.data is not None
        assert isinstance(result.data, CensusTable)


class TestPreprocessingPipeline:
    """Tests for PreprocessingPipeline."""

    def test_create_pipeline(self):
        """Test pipeline creation."""
        pipeline = PreprocessingPipeline(
            deskew=True,
            denoise=True,
            enhance_contrast=True,
            binarize=False,
        )

        assert "denoise" in pipeline.steps_applied
        assert "binarize" not in pipeline.steps_applied

    @pytest.mark.asyncio
    async def test_process_image(self):
        """Test image preprocessing."""
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="gray")

        pipeline = PreprocessingPipeline()
        result = await pipeline.process(img)

        # Should be converted to grayscale
        assert result.mode == "L"


class TestTextAlternative:
    """Tests for TextAlternative model."""

    def test_create_alternative(self):
        """Test alternative creation."""
        alt = TextAlternative(
            text="Denham",
            confidence=0.75,
        )

        assert alt.text == "Denham"
        assert alt.confidence == 0.75


class TestDocumentType:
    """Tests for DocumentType enum."""

    def test_document_types(self):
        """Test document type values."""
        assert DocumentType.CENSUS.value == "census"
        assert DocumentType.BIRTH_CERTIFICATE.value == "birth_certificate"
        assert DocumentType.NEWSPAPER.value == "newspaper"


class TestRecognitionConfidence:
    """Tests for RecognitionConfidence enum."""

    def test_confidence_levels(self):
        """Test confidence level values."""
        assert RecognitionConfidence.HIGH.value == "high"
        assert RecognitionConfidence.MEDIUM.value == "medium"
        assert RecognitionConfidence.LOW.value == "low"
        assert RecognitionConfidence.VERY_LOW.value == "very_low"
