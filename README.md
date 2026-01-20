# GPS Genealogy Agents

[![Wiki Preflight](https://github.com/thomasvincent/gps-genealogy-agents/actions/workflows/wiki-preflight.yml/badge.svg)](https://github.com/thomasvincent/gps-genealogy-agents/actions/workflows/wiki-preflight.yml)

Multi-agent AI genealogical research system meeting GPS (Genealogical Proof Standard).

# GPS Genealogy Agents

A multi-agent AI genealogical research system designed to produce conclusions that meet the **Genealogical Proof Standard (GPS)**.

Built with **Semantic Kernel** for plugin orchestration and **AutoGen** for multi-agent coordination, using Claude for complex reasoning and GPT-4 for structured tasks, with CQRS architecture (RocksDB ledger + SQLite projection) and **Gramps** integration.

## Features

- **GPS-Compliant**: All conclusions must satisfy the five GPS pillars
- **Multi-Agent Architecture**: 9 specialized agents using AutoGen SelectorGroupChat
- **Semantic Kernel Plugins**: Modular AI capabilities for citations, GPS evaluation, and reporting
- **Immutable Fact Ledger**: Append-only, versioned facts with full provenance
- **Smart Search Router**: Unified search across multiple genealogy databases
- **Gramps Integration**: Read/write access to local Gramps databases
- **Multiple LLM Providers**: Anthropic, OpenAI, Azure, Ollama

## Installation

```bash
# Clone the repository
git clone https://github.com/thomasvincent/gps-genealogy-agents.git
cd gps-genealogy-agents

# Install with uv
uv pip install -e ".[dev]"

# Optional: Install with all features
uv pip install -e ".[all]"

# Copy environment template
cp .env.example .env
# Edit .env with your API keys
```

## Quick Start

```python
import asyncio
from gps_agents.autogen import run_research_session

async def main():
    result = await run_research_session(
        "Find birth records for John Smith born circa 1842 in County Cork, Ireland"
    )
    for msg in result["messages"]:
        print(f"{msg['source']}: {msg['content'][:100]}...")

asyncio.run(main())
```

### CLI Usage

```bash
# Run a research query
gps-agents research "Find birth records for John Smith born circa 1842"

# Load a GEDCOM file
gps-agents load-gedcom ./my-family.ged

# View the fact ledger
gps-agents facts list --status ACCEPTED
```

## Architecture

```
User Request → SelectorGroupChat Coordinator
                        ↓
    ┌───────────────────┼───────────────────┐
    ↓                   ↓                   ↓
Research Agent   Translation Agent    DNA Agent
    ↓
Data Quality Agent (mechanical validation)
    ↓
┌───────────────┴───────────────┐
↓                               ↓
GPS Standards Critic      GPS Reasoning Critic
(Pillars 1 & 2)          (Pillars 3 & 4)
└───────────────┬───────────────┘
                ↓
         Citation Agent (Evidence Explained)
                ↓
         Synthesis Agent (Proof Narrative)
                ↓
         Workflow Agent (Ledger Write)
                ↓
    ACCEPTED Fact + GPS-Compliant Narrative
```

### Agents

| Agent | LLM | Role |
|-------|-----|------|
| Research | Claude | Record discovery from multiple sources |
| Data Quality | GPT-4 | Mechanical validation, error checking |
| GPS Standards Critic | Claude | Evaluates Pillars 1 (exhaustive search) & 2 (citations) |
| GPS Reasoning Critic | Claude | Evaluates Pillars 3 (analysis) & 4 (conflicts) |
| Workflow | GPT-4 | Orchestration, fact ledger writes |
| Citation | GPT-4 | Evidence Explained formatting |
| Synthesis | Claude | Proof narratives, GPS Pillar 5 |
| Translation | GPT-4 | Foreign language records |
| DNA/Ethnicity | GPT-4 | Probabilistic interpretation |

### GPS Pillars

1. **Reasonably Exhaustive Search** - Major source classes checked, negative results documented
2. **Complete & Accurate Citations** - Evidence Explained compliant
3. **Analysis & Correlation** - Direct, indirect, and negative evidence classified
4. **Conflict Resolution** - Contradictions identified and resolved
5. **Written Conclusion** - Coherent proof summary produced

## Semantic Kernel Plugins

| Plugin | Functions |
|--------|-----------|
| **CitationPlugin** | `format_citation`, `classify_evidence` |
| **GPSPlugin** | `evaluate_pillar_1` through `evaluate_pillar_5` |
| **ReportsPlugin** | `generate_proof_summary`, `format_research_log_entry`, `generate_evidence_table` |
| **MemoryPlugin** | `save_research_context`, `recall_research` |
| **SourcesPlugin** | `search_familysearch`, `search_wikitree`, etc. |
| **LedgerPlugin** | `propose_fact`, `accept_fact`, `get_fact_history` |

## Data Sources

The Smart Search Router provides unified access to:

- **FamilySearch** - OAuth2 API
- **WikiTree** - Public API + scraping
- **FindMyPast** - API (subscription required)
- **MyHeritage** - API (subscription required)
- **AccessGenealogy** - Web scraping (Native American records)
- **Jerripedia** - Web scraping (Channel Islands)
- **GEDCOM** - Local file parsing
- **Gramps** - Local database access

### Region-Aware Routing

```python
from gps_agents.sources import SearchRouter, Region

router = SearchRouter()
router.register_source(FamilySearchSource())
router.register_source(WikiTreeSource())

# Automatically routes to relevant sources
result = await router.search_person(
    surname="Herinckx",
    birth_year=1895,
    region=Region.BELGIUM
)
```

## Gramps Integration

```python
from gps_agents.gramps import GrampsClient

# Connect to local Gramps database
client = GrampsClient("/path/to/gramps/family-tree")
client.connect()

# Search for persons
persons = client.find_persons(surname="Smith", given="John")

# Get database statistics
stats = client.get_statistics()
print(f"Persons: {stats['person']}, Families: {stats['family']}")
```

## Development

```bash
# Run tests
uv run pytest

# Run linting
uv run ruff check .

# Type checking
uv run mypy src/

# Format code
uv run ruff format .
```

## Configuration

Create a `.env` file with your API keys:

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
FAMILYSEARCH_API_KEY=...
```

## License

MIT License - see [LICENSE](LICENSE) for details.
