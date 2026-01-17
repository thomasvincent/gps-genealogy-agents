# GPS Genealogy Multi-Agent System Design

**Date:** 2026-01-17
**Status:** Approved

## Overview

A multi-agent AI genealogical research system designed to produce conclusions that meet the Genealogical Proof Standard (GPS). Built with LangGraph for orchestration, using a mixed LLM strategy (Claude for reasoning, GPT-4 for structured tasks), and CQRS architecture with RocksDB ledger + SQLite projection.

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Orchestration | LangGraph | Native state management, conditional routing |
| Reasoning LLM | Claude | Complex analysis, GPS critics |
| Task LLM | GPT-4 | Structured outputs, citations |
| Write Store | RocksDB | Append-only, immutable ledger |
| Read Store | SQLite | Fast queries, projections |

## Project Structure

```
gps-genealogy-agents/
├── README.md
├── pyproject.toml
├── .env.example
├── prompts/
│   ├── system_root.txt
│   ├── workflow_agent.txt
│   ├── research_agent.txt
│   ├── data_quality_agent.txt
│   ├── gps_standards_critic.txt
│   ├── gps_reasoning_critic.txt
│   ├── translation_agent.txt
│   ├── ethnicity_dna_agent.txt
│   ├── citation_agent.txt
│   └── synthesis_agent.txt
├── src/
│   └── gps_agents/
│       ├── __init__.py
│       ├── graph.py              # LangGraph orchestration
│       ├── agents/               # Agent implementations
│       ├── ledger/               # RocksDB fact ledger
│       ├── projections/          # SQLite read model
│       ├── sources/              # Data source connectors
│       └── models/               # Pydantic schemas
└── tests/
```

## Agent → LLM Mapping

| Agent | LLM | Rationale |
|-------|-----|-----------|
| Workflow Agent | Claude | Complex orchestration decisions |
| GPS Standards Critic | Claude | Evaluates research exhaustiveness |
| GPS Reasoning Critic | Claude | Analyzes logic, resolves conflicts |
| Synthesis Agent | Claude | Produces proof narratives |
| Research Agent | GPT-4 | Structured search queries |
| Data Quality Agent | GPT-4 | Mechanical validation |
| Translation Agent | GPT-4 | Linguistic tasks |
| Citation Agent | GPT-4 | Formatting to Evidence Explained |
| Ethnicity/DNA Agent | GPT-4 | Probabilistic interpretation |

## Data Models

### Fact (Core Entity)

```python
class Fact(BaseModel):
    fact_id: UUID
    version: int
    statement: str                    # "John Smith born 1842 in County Cork"
    sources: list[SourceCitation]
    provenance: Provenance            # Who/what created this, when
    confidence_score: float           # 0.0 - 1.0
    confidence_history: list[ConfidenceDelta]
    status: Literal["PROPOSED", "ACCEPTED", "REJECTED", "INCOMPLETE"]
    annotations: list[Annotation]
    created_at: datetime

class SourceCitation(BaseModel):
    repository: str                   # "FamilySearch", "WikiTree", etc.
    record_id: str
    url: str | None
    accessed_at: datetime
    evidence_type: Literal["DIRECT", "INDIRECT", "NEGATIVE"]

class ConfidenceDelta(BaseModel):
    agent: str                        # Which agent adjusted
    delta: float                      # +/- adjustment
    reason: str
    timestamp: datetime
```

### GPS Evaluation

```python
class GPSEvaluation(BaseModel):
    # Pillar 1: Reasonably Exhaustive Search
    pillar_1: PillarStatus
    sources_searched: list[str]
    sources_missing: list[str]
    search_exhaustive: bool

    # Pillar 2: Complete & Accurate Citations
    pillar_2: PillarStatus
    citations_valid: bool
    evidence_explained_compliant: bool
    citation_issues: list[str]

    # Pillar 3: Analysis & Correlation
    pillar_3: PillarStatus
    evidence_correlation: str
    informant_reliability: dict[str, str]

    # Pillar 4: Conflict Resolution
    pillar_4: PillarStatus
    conflicts_identified: list[Conflict]
    conflicts_resolved: bool
    resolution_reasoning: str | None

    # Pillar 5: Written Conclusion
    pillar_5: PillarStatus
    proof_summary: str | None

class PillarStatus(str, Enum):
    SATISFIED = "satisfied"
    PARTIAL = "partial"
    FAILED = "failed"
    PENDING = "pending"
```

## Storage Architecture (CQRS)

### RocksDB Ledger (Write Model)
- Key: `{fact_id}:{version}`
- Value: JSON-serialized Fact
- Append-only: new versions create new keys
- Column families: `facts`, `indexes`, `events`

### SQLite Projection (Read Model)
- Denormalized for fast queries
- Rebuilt from ledger on startup
- Indexes on person, date, place, status

## Data Source Connectors

```
sources/
├── base.py              # Protocol + SearchQuery model
├── familysearch.py      # OAuth2, REST API
├── wikitree.py          # Public API + scraping
├── findmypast.py        # Requires subscription key
├── myheritage.py        # Requires subscription key
├── accessgenealogy.py   # Web scraping (Native American records)
├── jerripedia.py        # Web scraping (Channel Islands)
├── gedcom.py            # Local file parser
└── fallback_scraper.py  # Generic archive scraper
```

### Search Query Model

```python
class SearchQuery(BaseModel):
    given_name: str | None
    surname: str | None
    surname_variants: list[str] = []
    birth_year: int | None
    birth_year_range: int = 5
    birth_place: str | None
    death_year: int | None
    residence: str | None
    record_types: list[str] = []
```

### Fallback Strategy
1. Try APIs first (FamilySearch → WikiTree → paid sources)
2. Fall back to scraping if API unavailable
3. All results include full provenance

## Workflow Graph

```
User Request → Workflow Agent → [Research | Translation | DNA]
                                        ↓
                              Data Quality Agent
                                        ↓
                    [GPS Standards Critic | GPS Reasoning Critic]
                                        ↓
                            Confidence < 0.7? → Retry (max 2)
                                        ↓
                              Citation Agent
                                        ↓
                              Synthesis Agent
                                        ↓
                            ACCEPTED Fact + Narrative
```

## GPS Enforcement Rules

- All 5 pillars must be `SATISFIED` for status → `ACCEPTED`
- Any `FAILED` pillar triggers Search Revision Request
- `PARTIAL` triggers targeted follow-up
- Conflicts MUST be explicitly resolved OR fact stays `INCOMPLETE`
- Confidence < 0.7 after critic review → automatic retry (max 2)
- Every status change logged with timestamp, agent, and reasoning

## Next Steps

1. Create GitHub repository
2. Write prompt files
3. Implement core models (Pydantic schemas)
4. Implement RocksDB ledger
5. Implement SQLite projection
6. Build data source connectors
7. Create LangGraph workflow
8. Implement each agent
9. Add CLI interface
10. Write tests
