# GPS Genealogy Agents

A multi-agent AI genealogical research system designed to produce conclusions that meet the **Genealogical Proof Standard (GPS)**.

Built with LangGraph for orchestration, using Claude for complex reasoning and GPT-4 for structured tasks, with a CQRS architecture (RocksDB ledger + SQLite projection).

## Features

- **GPS-Compliant**: All conclusions must satisfy the five GPS pillars
- **Multi-Agent Architecture**: Specialized agents for research, validation, critique, and synthesis
- **Immutable Fact Ledger**: Append-only, versioned facts with full provenance
- **Multiple Data Sources**: FamilySearch, WikiTree, FindMyPast, MyHeritage, AccessGenealogy, Jerripedia, GEDCOM files

## Installation

```bash
# Clone the repository
git clone https://github.com/thomasvincent/gps-genealogy-agents.git
cd gps-genealogy-agents

# Install with uv
uv pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
# Edit .env with your API keys
```

## Quick Start

```bash
# Run a research query
gps-agents research "Find birth records for John Smith born circa 1842 in County Cork, Ireland"

# Load a GEDCOM file
gps-agents load-gedcom ./my-family.ged

# View the fact ledger
gps-agents facts list --status ACCEPTED
```

## Architecture

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

### Agents

| Agent | LLM | Role |
|-------|-----|------|
| Workflow | Claude | Orchestration, ledger writes |
| Research | GPT-4 | Record discovery |
| Data Quality | GPT-4 | Mechanical validation |
| GPS Standards Critic | Claude | Pillars 1 & 2 evaluation |
| GPS Reasoning Critic | Claude | Pillars 3 & 4 evaluation |
| Translation | GPT-4 | Foreign language records |
| Citation | GPT-4 | Evidence Explained formatting |
| Synthesis | Claude | Proof narratives |
| DNA/Ethnicity | GPT-4 | Probabilistic interpretation |

### GPS Pillars

1. **Reasonably Exhaustive Search** - Major source classes checked
2. **Complete & Accurate Citations** - Evidence Explained compliant
3. **Analysis & Correlation** - Evidence properly weighed
4. **Conflict Resolution** - Contradictions addressed
5. **Written Conclusion** - Proof summary produced

## Data Sources

- **FamilySearch** - OAuth2 API
- **WikiTree** - Public API + scraping
- **FindMyPast** - API (subscription required)
- **MyHeritage** - API (subscription required)
- **AccessGenealogy** - Web scraping (Native American records)
- **Jerripedia** - Web scraping (Channel Islands)
- **GEDCOM** - Local file parsing

## Development

```bash
# Run tests
pytest

# Run linting
ruff check .

# Type checking
mypy src/
```

## License

MIT License - see [LICENSE](LICENSE) for details.
