# Publishing Manager Architecture

The Publishing Manager orchestrates synchronized publishing of genealogical research across multiple platforms (Wikipedia, Wikidata, WikiTree, GitHub) while maintaining GPS (Genealogical Proof Standard) compliance.

## Overview

The Publishing Manager implements a multi-stage validation pipeline:

```
Research Complete → GPS Grading → Quorum Review → Integrity Check → Platform Publishing
```

## Key Components

### GPS Grade Card

Research is scored against the five GPS pillars on a 1-10 scale:

| Pillar | Description |
|--------|-------------|
| Reasonably Exhaustive Search | Have relevant sources been consulted? |
| Complete Citations | Are all claims properly cited? |
| Analysis and Correlation | Has evidence been analyzed and correlated? |
| Conflict Resolution | Have contradictions been resolved? |
| Written Conclusion | Is there a coherent proof argument? |

**Grading Scale:**

| Grade | Score Range | Allowed Platforms |
|-------|-------------|-------------------|
| A | 9.0 - 10.0 | Wikipedia, Wikidata, WikiTree, GitHub |
| B | 8.0 - 8.9 | WikiTree, GitHub |
| C | 7.0 - 7.9 | GitHub only |
| D | 6.0 - 6.9 | Not publishable |
| F | Below 6.0 | Not publishable |

### Quorum Review System

Two independent reviewers must both PASS for publication approval:

**Logic Reviewer** validates:
- Timeline consistency (events in chronological order)
- Relationship validity (no circular relationships, valid age gaps)
- Impossible claims detection (events before birth, after death)

**Source Reviewer** validates:
- Citation validity (all key facts have sources)
- Evidence sufficiency (primary sources for vital events)
- Source authenticity (no fabricated records)

### Integrity Guard

The Integrity Guard enforces publishing rules based on issue severity:

| Severity | Impact |
|----------|--------|
| CRITICAL | Blocks ALL platforms |
| HIGH | Blocks Wikipedia and Wikidata |
| MEDIUM | Warning (blocks Wikipedia in strict mode) |
| LOW | Informational only |

### Paper Trail of Doubt

Preserves intellectual honesty by documenting:

- **Research Notes**: Methodology and findings
- **Uncertainties**: Known limitations with confidence levels
- **Unresolved Conflicts**: Competing claims that cannot be definitively resolved

## Workflow

### 1. Prepare for Publishing

```python
from gps_agents.genealogy_crawler import PublishingManager, MockLLMClient

manager = PublishingManager(MockLLMClient())

pipeline = manager.prepare_for_publishing(
    subject_id="person_123",
    subject_name="John Smith",
    source_count=15,
    source_tiers={"tier_0": 8, "tier_1": 5, "tier_2": 2},
    citation_count=45,
    total_claims=50,
    conflicts_found=3,
    conflicts_resolved=2,
    uncertainties_documented=1,
    has_written_conclusion=True,
)

print(f"Grade: {pipeline.grade_card.letter_grade}")  # e.g., "A"
print(f"Allowed platforms: {pipeline.grade_card.allowed_platforms}")
```

### 2. Run Quorum Review

```python
quorum = manager.run_quorum(
    pipeline=pipeline,
    events=[...],  # Timeline events
    claims=[...],  # Claims to verify
    claims_with_citations=[...],  # Claims paired with sources
    source_summaries=[...],  # Source metadata
    key_facts=[...],  # Critical facts to verify
    subject_name="John Smith",
)

if quorum.approved:
    print("Quorum approved for publishing")
else:
    print(f"Blocking issues: {quorum.blocking_issues}")
```

### 3. Check Integrity and Finalize

```python
can_publish, allowed = manager.check_integrity(pipeline)

if can_publish:
    pipeline = manager.finalize_for_publishing(pipeline)
    print(f"Ready to publish to: {pipeline.effective_platforms}")
```

### 4. Add Paper Trail Items

```python
# Document an uncertainty
manager.add_uncertainty(
    pipeline=pipeline,
    field="birth_date",
    description="Two sources disagree by 2 years",
    confidence_level=0.75,
    alternative_interpretations=[
        "1845 from census (self-reported)",
        "1847 from birth certificate"
    ],
    additional_sources_needed=["Parish baptism records"]
)

# Document an unresolved conflict
manager.add_unresolved_conflict(
    pipeline=pipeline,
    field="death_location",
    competing_claims=[
        {"value": "Chicago, IL", "source": "Death certificate"},
        {"value": "Springfield, IL", "source": "Newspaper obituary"}
    ],
    analysis_summary="Both sources are primary, newspaper may have misreported",
    remaining_doubt="Unable to confirm which location is correct",
    chosen_value="Chicago, IL",
    chosen_rationale="Death certificate is official record"
)
```

## Integration with Orchestrator

The Publishing Manager can be integrated with the Orchestrator for end-to-end research:

```python
from gps_agents.genealogy_crawler import Orchestrator, PublishingManager

# Create with publishing manager
manager = PublishingManager(llm_client)
orchestrator = Orchestrator(
    llm_client=llm_client,
    publishing_manager=manager,
)

# Run research
state = orchestrator.initialize_from_seed(seed_person)
final_state = orchestrator.run(state)

# Finalize for publishing
pipeline = orchestrator.finalize_research(
    state=final_state,
    subject_id=str(seed_person.id),
    subject_name=seed_person.canonical_name,
)
```

## Module Structure

```
src/gps_agents/genealogy_crawler/publishing/
├── __init__.py         # Module exports
├── models.py           # Pydantic models (GPSGradeCard, QuorumDecision, etc.)
├── manager.py          # PublishingManager orchestration class
├── reviewers.py        # LLM wrappers (GPSGraderLLM, LogicReviewer, SourceReviewer, LinguistLLM)
└── validators/
    ├── __init__.py
    ├── gps_pillars.py  # Heuristic GPS pillar validation
    └── integrity.py    # Issue severity and platform blocking
```

### Linguist Agent

The Linguist Agent specializes in content generation for Wikipedia and WikiTree:

| Task | Description |
|------|-------------|
| Wikipedia Draft | Encyclopedic NPOV lead paragraph with infobox |
| WikiTree Bio | Collaborative narrative with community templates |
| GPS Pillar 5 Grade | Score for Written Conclusion (1-10) |
| Markdown DIFF | Improvements for local article |

**Key Constraint:** The Linguist only consumes ACCEPTED facts with confidence >= 0.9.

```python
from gps_agents.genealogy_crawler import (
    PublishingManager,
    LinguistLLM,
    AcceptedFact,
)

manager = PublishingManager(llm_client)
pipeline = manager.create_pipeline("person_123")

# Facts must have status="ACCEPTED" and confidence >= 0.9
facts = [
    {"field": "birth_date", "value": "1850-03-15", "status": "ACCEPTED", "confidence": 0.95},
    {"field": "birth_place", "value": "Boston, MA", "status": "ACCEPTED", "confidence": 0.92},
]

# Generate wiki content
output = manager.generate_wiki_content(
    pipeline=pipeline,
    subject_name="John Smith",
    facts=facts,
    wikidata_qid="Q12345",
    generate_wikipedia=True,
    generate_wikitree=True,
)

print(f"GPS Pillar 5: {output.gps_pillar_5_grade.score}/10")
print(f"Wikipedia: {output.wikipedia_draft.lead_paragraph}")
print(f"WikiTree: {output.wikitree_bio.narrative}")
```

**Uncertainty Handling:**
- Facts with confidence < 0.9 are filtered out
- Uncertainties from Paper Trail are passed to Linguist
- Output includes RESEARCH_NOTES section with open questions

## LLM Prompts

The following system prompts are used:

| Role | Purpose |
|------|---------|
| `gps_grader` | Scores research against 5 GPS pillars |
| `publishing_logic_reviewer` | Validates timeline and relationship consistency |
| `publishing_source_reviewer` | Validates citations and evidence sufficiency |
| `linguist` | Generates Wikipedia/WikiTree content from ACCEPTED facts |

## Design Principles

1. **GPS Compliance**: All published research must meet the Genealogical Proof Standard
2. **Dual Review Quorum**: Two independent reviewers provide checks and balances
3. **Graduated Access**: Higher-quality research unlocks more prestigious platforms
4. **Paper Trail of Doubt**: Honest documentation of limitations and uncertainties
5. **Integrity Guard**: Blocking of problematic content before publication
