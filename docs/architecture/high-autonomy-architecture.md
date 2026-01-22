# High-Autonomy Genealogy Research Architecture

## System Overview

This document describes the high-autonomy architecture for GPS-compliant genealogical research, integrating four major components:

1. **LLM-Native Web Scraping** - Structured extraction with CensusHousehold schema
2. **High-Scale Probabilistic Linkage** - Splink entity resolution
3. **Neo4j Graph Projection** - CQRS for pedigree traversal
4. **Historical OCR Agent** - Kraken for handwritten documents

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GPS Genealogy Research System                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │   Web Sources   │     │  Document OCR   │     │  API Sources    │       │
│  │  (Ancestry,     │     │  (Census Images,│     │  (FamilySearch, │       │
│  │   FindAGrave)   │     │   Vital Records)│     │   WikiTree)     │       │
│  └────────┬────────┘     └────────┬────────┘     └────────┬────────┘       │
│           │                       │                       │                 │
│           ▼                       ▼                       ▼                 │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                    LLM-Native Extraction Layer                   │       │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │       │
│  │  │ CensusHousehold │  │  KrakenOCRAgent │  │   APIExtractor  │  │       │
│  │  │   Extractor     │  │                 │  │                 │  │       │
│  │  │ (ScrapeGraphAI) │  │  (Handwritten)  │  │ (Structured)    │  │       │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘  │       │
│  └─────────────────────────────────┬───────────────────────────────┘       │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                 Probabilistic Linkage Engine                     │       │
│  │  ┌─────────────────────────────────────────────────────────────┐│       │
│  │  │                    SplinkEntityResolver                      ││       │
│  │  │  • Blocking (Soundex, first letter, birth year)             ││       │
│  │  │  • Fellegi-Sunter scoring (m/u probabilities)               ││       │
│  │  │  • EM training for parameter estimation                      ││       │
│  │  │  • Cluster generation with confidence thresholds             ││       │
│  │  └─────────────────────────────────────────────────────────────┘│       │
│  └─────────────────────────────────┬───────────────────────────────┘       │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                      CQRS Storage Layer                          │       │
│  │                                                                   │       │
│  │  ┌─────────────────┐        ┌─────────────────────────────────┐ │       │
│  │  │  RocksDB Ledger │──sync──│     Neo4j Graph Projection      │ │       │
│  │  │ (Source of Truth)│        │  (Ancestor/Descendant Queries) │ │       │
│  │  │                 │        │                                  │ │       │
│  │  │ • Evidence      │        │  • PedigreeTraversal            │ │       │
│  │  │ • Assertions    │        │  • KinshipComputation           │ │       │
│  │  │ • Provenance    │        │  • FamilyUnitReconstruction     │ │       │
│  │  └─────────────────┘        └─────────────────────────────────┘ │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                      GPS Adjudication Gate                       │       │
│  │  • LogicReviewer + SourceReviewer quorum                        │       │
│  │  • Grade Card scoring (A/B/C/D/F)                               │       │
│  │  • Publishing decisions (Wikipedia, Wikidata, WikiTree, GitHub) │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. LLM-Native Web Scraping

**Location:** `src/gps_agents/genealogy_crawler/extraction/`

**Key Classes:**
- `StructuredCensusHousehold` - Target extraction schema
- `StructuredCensusPerson` - Person with name variants, confidence
- `CensusHouseholdExtractor` - Anthropic/OpenAI extraction
- `ScrapeGraphAIExtractor` - Optional ScrapeGraphAI integration

**Token Reduction:** 67% vs raw HTML by extracting structured objects

**Example:**
```python
extractor = CensusHouseholdExtractor(provider="anthropic")
result = await extractor.extract_from_url(
    "https://ancestry.com/census/1940/durham",
    census_year=1940,
    target_surname="Durham",
)
household = result.data  # StructuredCensusHousehold
```

### 2. High-Scale Probabilistic Linkage

**Location:** `src/gps_agents/genealogy_crawler/linkage/`

**Key Classes:**
- `SplinkEntityResolver` - Main resolver using Splink library
- `FeatureComparison` - Fellegi-Sunter weights per field
- `MatchCandidate` - Potential match with confidence
- `EntityCluster` - Resolved entity with member records
- `CensusComparisonConfig` - Census-optimized blocking rules

**Algorithm:**
1. Blocking: Reduce O(n²) to manageable pairs
2. Comparison: Jaro-Winkler for names, numeric distance for years
3. Scoring: Log-likelihood ratios combined
4. Clustering: Group records above threshold

**Example:**
```python
resolver = SplinkEntityResolver(
    comparison_config=CensusComparisonConfig(),
    threshold=0.85,
)
result = await resolver.resolve(census_records)
for cluster in result.clusters:
    print(f"{cluster.canonical_name}: {cluster.size} records")
```

### 3. Neo4j Graph Projection (CQRS)

**Location:** `src/gps_agents/genealogy_crawler/graph/`

**Key Classes:**
- `GraphProjection` - CQRS sync from RocksDB to Neo4j
- `PedigreeTraversal` - Ancestor/descendant queries
- `Neo4jPedigreeTraversal` - Optimized Cypher queries
- `PersonProjector` - Project persons to graph nodes
- `KinshipResult` - Relationship computation results

**Architecture:**
- **Write Side:** RocksDB ledger (immutable evidence)
- **Read Side:** Neo4j graph (optimized traversal)
- **Sync:** Event-driven projection updates

**Example:**
```python
traversal = PedigreeTraversal(neo4j_store)
result = await traversal.get_ancestors(
    person_id=archie_durham_id,
    max_generations=4,
)
for ancestor in result.ancestors:
    print(f"Gen {ancestor['generation']}: {ancestor['person']['name']}")
```

### 4. Historical OCR Agent

**Location:** `src/gps_agents/genealogy_crawler/ocr/`

**Key Classes:**
- `KrakenOCRAgent` - General historical document OCR
- `CensusOCRAgent` - Census table structure extraction
- `RecognizedPage` - Page with regions, lines, words
- `CensusTable` - Structured census extraction
- `PreprocessingPipeline` - Image enhancement

**Features:**
- Baseline detection for handwritten text
- Census column mapping (Name, Age, Birthplace, etc.)
- LLM post-processing for ambiguous characters
- Confidence scoring with review flagging

**Example:**
```python
agent = CensusOCRAgent(census_year=1940)
result = await agent.extract_census_table("census_page.jpg")
for row in result.data.rows:
    print(f"{row.name}, age {row.age}")
```

## GPS Compliance Mapping

| GPS Pillar | Component | Implementation |
|------------|-----------|----------------|
| **1. Exhaustive Search** | Web Scraping + OCR | Multi-source extraction (Ancestry, FamilySearch, newspapers) |
| **2. Complete Citation** | ExtractionProvenance | Every extracted fact has source URL, timestamp, confidence |
| **3. Information Analysis** | FeatureComparison | Primary vs derivative scoring, m/u probabilities |
| **4. Correlation Resolution** | SplinkEntityResolver | Probabilistic linkage with conflict detection |
| **5. Soundly Reasoned Conclusion** | GPSGradeCard | Automated scoring, quorum review, publish decisions |

### GPS Grade Card Mapping

| Grade | Score | Allowed Platforms |
|-------|-------|-------------------|
| A | 9.0-10.0 | Wikipedia, Wikidata, WikiTree, GitHub |
| B | 8.0-8.9 | WikiTree, GitHub only |
| C | 7.0-7.9 | GitHub only |
| D | 6.0-6.9 | Not publishable |
| F | <6.0 | Not publishable |

## Data Flow

```
1. Discovery
   URLs/Images → LLM Extraction / Kraken OCR → StructuredCensusHousehold

2. Linkage
   Multiple Records → SplinkEntityResolver → EntityClusters

3. Storage
   EntityClusters → RocksDB Ledger → Neo4j Projection

4. Query
   Pedigree Query → Neo4jPedigreeTraversal → Ancestors/Descendants

5. Review
   Research Output → GPS Grade Card → Quorum Review → Publish Decision
```

## Module Structure

```
src/gps_agents/genealogy_crawler/
├── extraction/           # LLM-Native Web Scraping
│   ├── models.py         # StructuredCensusHousehold, ExtractionResult
│   ├── extractors.py     # CensusHouseholdExtractor
│   └── __init__.py
├── linkage/              # Probabilistic Linkage
│   ├── models.py         # FeatureComparison, EntityCluster, LinkageResult
│   ├── configs.py        # CensusComparisonConfig, VitalRecordConfig
│   ├── resolver.py       # SplinkEntityResolver
│   └── __init__.py
├── graph/                # Neo4j CQRS Projection
│   ├── graph_store.py    # Neo4jGraphStore, RocksDBGraphStore
│   ├── models.py         # PedigreeQuery, KinshipResult, FamilyUnit
│   ├── projection.py     # GraphProjection, PersonProjector
│   ├── traversal.py      # PedigreeTraversal, Neo4jPedigreeTraversal
│   └── __init__.py
├── ocr/                  # Historical OCR
│   ├── models.py         # RecognizedPage, CensusTable, BoundingBox
│   ├── agents.py         # KrakenOCRAgent, CensusOCRAgent
│   └── __init__.py
└── publishing/           # GPS Adjudication
    ├── models.py         # GPSGradeCard, QuorumDecision
    ├── manager.py        # PublishingManager
    └── __init__.py
```

## Test Coverage

| Module | Tests | Status |
|--------|-------|--------|
| extraction | 19 | ✅ Pass |
| linkage | 25 | ✅ Pass |
| graph | 30 | ✅ Pass |
| ocr | 37 | ✅ Pass |
| **Total** | **111** | ✅ All Pass |

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Web extraction | < 5s/page | LLM API latency |
| OCR recognition | < 2s/page | Kraken on CPU |
| Entity resolution | 10K records/min | Splink with DuckDB |
| Ancestor query | < 100ms | Neo4j Cypher |
| Kinship computation | < 500ms | BFS with caching |

## Configuration

### Environment Variables

```bash
# LLM Providers
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=genealogy

# Storage
ROCKSDB_PATH=/data/ledger
```

### Kraken Models

Download required models for historical OCR:
```bash
kraken get blla.mlmodel  # Baseline detection
kraken get en_best.mlmodel  # English recognition
```

## Future Enhancements

1. **Streaming OCR** - Process large document sets in batches
2. **Active Learning** - Improve linkage with human feedback
3. **Timeline Visualization** - Interactive family timelines
4. **DNA Integration** - Incorporate genetic genealogy data
5. **Multi-Language OCR** - Support German, Swedish, Italian scripts
