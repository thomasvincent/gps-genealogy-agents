# GPS Genealogy Agents: Semantic Kernel + AutoGen Port

## Overview

Port the GPS Genealogy Agents system from LangGraph to Microsoft Semantic Kernel (SK) + AutoGen for improved modularity, native multi-agent coordination, and enhanced memory capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AutoGen GroupChatManager                      │
│                  (Speaker Selection + Routing)                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
    ┌─────────────────────┼─────────────────────┐
    │                     │                     │
    ▼                     ▼                     ▼
┌──────────┐        ┌──────────┐         ┌──────────┐
│ Research │        │   GPS    │         │ Workflow │
│  Agent   │        │ Critics  │         │  Agent   │
│(GPT-4)   │        │(Claude)  │         │(GPT-4)   │
└────┬─────┘        └────┬─────┘         └────┬─────┘
     │                   │                    │
     └───────────────────┼────────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │    SK Kernel        │
              │  ┌───────────────┐  │
              │  │   Plugins     │  │
              │  │ - Ledger      │  │
              │  │ - Sources     │  │
              │  │ - GPS         │  │
              │  │ - Citation    │  │
              │  │ - Memory      │  │
              │  └───────────────┘  │
              └──────────┬──────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │ RocksDB  │    │  SQLite  │    │ ChromaDB │
   │ (Ledger) │    │(Project) │    │ (Memory) │
   └──────────┘    └──────────┘    └──────────┘
```

## Component Design

### 1. SK Plugins

#### LedgerPlugin
```python
@kernel_function(description="Append a fact to the immutable ledger")
async def append_fact(self, fact_json: str) -> str:
    fact = Fact.model_validate_json(fact_json)
    key = self.ledger.append(fact)
    return f"Fact appended with key: {key}"

@kernel_function(description="Get a fact by ID with optional version")
async def get_fact(self, fact_id: str, version: int | None = None) -> str:
    fact = self.ledger.get(UUID(fact_id), version)
    return fact.model_dump_json() if fact else "Fact not found"
```

#### SourcesPlugin
```python
@kernel_function(description="Search FamilySearch for records")
async def search_familysearch(self, query_json: str) -> str:
    query = SearchQuery.model_validate_json(query_json)
    records = await self.familysearch.search(query)
    return json.dumps([r.model_dump() for r in records])
```

#### GPSPlugin
```python
@kernel_function(description="Evaluate fact against GPS Pillar 1")
async def evaluate_pillar_1(self, fact_json: str) -> str:
    # Reasonably exhaustive search evaluation
    ...

@kernel_function(description="Check if fact meets acceptance criteria")
async def can_accept_fact(self, fact_json: str) -> str:
    fact = Fact.model_validate_json(fact_json)
    return json.dumps({"can_accept": fact.can_accept()})
```

### 2. AutoGen Agents

Each agent is an `AssistantAgent` with access to the shared SK Kernel:

| Agent | Model | Primary Plugins |
|-------|-------|-----------------|
| research_agent | GPT-4 | Sources, Memory |
| data_quality_agent | GPT-4 | Ledger |
| gps_standards_critic | Claude | GPS, Ledger |
| gps_reasoning_critic | Claude | GPS, Ledger |
| workflow_agent | GPT-4 | Ledger (write access) |
| citation_agent | GPT-4 | Citation |
| synthesis_agent | Claude | Memory, Ledger |
| translation_agent | GPT-4 | - |
| dna_agent | GPT-4 | Memory |

### 3. GroupChat Orchestration

The `GroupChatManager` coordinates agent interactions:

- **Speaker Selection**: LLM-based routing based on conversation context
- **Termination**: When fact status is ACCEPTED or REJECTED
- **Max Rounds**: 50 (configurable)
- **Write Control**: Only `workflow_agent` can call `append_fact`

### 4. SK Memory (ChromaDB)

Collections:
- `facts`: Fact statements for semantic similarity search
- `sources`: Source citations for deduplication
- `research_context`: Historical research patterns

## Migration Path

1. Keep existing storage layer (RocksDB/JSON + SQLite)
2. Add SK plugins as thin wrappers around existing services
3. Replace LangGraph agents with AutoGen AssistantAgents
4. Add ChromaDB for semantic memory
5. Update CLI to use new orchestration

## Dependencies

```toml
[project.dependencies]
semantic-kernel = ">=1.0.0"
pyautogen = ">=0.2.0"
chromadb = ">=0.4.0"
# ... existing dependencies
```

## File Structure

```
src/gps_agents/
├── sk/
│   ├── __init__.py
│   ├── kernel.py          # Kernel setup
│   └── plugins/
│       ├── __init__.py
│       ├── ledger.py      # LedgerPlugin
│       ├── sources.py     # SourcesPlugin
│       ├── gps.py         # GPSPlugin
│       ├── citation.py    # CitationPlugin
│       └── memory.py      # MemoryPlugin
├── autogen/
│   ├── __init__.py
│   ├── agents.py          # Agent definitions
│   └── orchestration.py   # GroupChat setup
└── ... (existing files)
```

## GPS Enforcement

All 5 GPS pillars must be SATISFIED before fact acceptance:

1. **Reasonably Exhaustive Search**: Sources plugin tracks search coverage
2. **Complete Citations**: Citation plugin enforces Evidence Explained format
3. **Analysis & Correlation**: GPS critics evaluate evidence correlation
4. **Conflict Resolution**: Critics identify and resolve contradictions
5. **Sound Conclusion**: Synthesis agent generates proof argument

The `workflow_agent` verifies all pillars before writing ACCEPTED status.
