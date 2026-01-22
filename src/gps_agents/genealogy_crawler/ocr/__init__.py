"""Historical OCR module for genealogical document recognition.

Provides Kraken-based OCR for:
- Handwritten historical documents (census records, vital records)
- Table structure extraction
- LLM-assisted post-processing

Key components:
- KrakenOCRAgent: General historical document OCR
- CensusOCRAgent: Specialized census table extraction
- PreprocessingPipeline: Image enhancement for OCR
"""
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
    RecognitionConfidence,
    RecognizedChar,
    RecognizedLine,
    RecognizedPage,
    RecognizedRegion,
    RecognizedWord,
    TextAlternative,
)
from .agents import (
    CensusOCRAgent,
    KrakenOCRAgent,
    OCRAgent,
    PreprocessingPipeline,
)

__all__ = [
    # Models
    "BoundingBox",
    "Baseline",
    "TextAlternative",
    "RecognizedChar",
    "RecognizedWord",
    "RecognizedLine",
    "RecognizedRegion",
    "RecognizedPage",
    "OCRProvenance",
    "OCRResult",
    "OCREngine",
    "DocumentType",
    "RecognitionConfidence",
    # Census models
    "CensusColumn",
    "CensusCell",
    "CensusRow",
    "CensusTable",
    # Agents
    "OCRAgent",
    "KrakenOCRAgent",
    "CensusOCRAgent",
    "PreprocessingPipeline",
]
