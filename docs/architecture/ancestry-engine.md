# The Ancestry Engine: Multi-Agent Genealogical Research System

## Overview

The Ancestry Engine is an autonomous multi-agent system designed for genealogical research following the Genealogical Proof Standard (GPS). It employs four specialized agents coordinated through a Plan-and-Execute loop implemented in LangGraph.

## System Architecture

```mermaid
flowchart TB
    subgraph Input
        Q[Research Query]
        SEED[Seed Person Data]
    end

    subgraph "The Ancestry Engine"
        subgraph Orchestration["Orchestration Layer"]
            LEAD[🎯 The Lead<br/>Task Decomposition<br/>State Management]
            FQ[(FrontierQueue<br/>Prioritized Tasks)]
            STATE[(Research State<br/>Knowledge Graph)]
        end

        subgraph Agents["Agent Pool"]
            SCOUT[🔍 The Scout<br/>Tool-Use Specialist<br/>Search/Browse/Scrape]
            ANALYST[🧠 The Analyst<br/>Conflict Resolution<br/>Clue Generation]
            CENSOR[🛡️ The Censor<br/>PII Compliance<br/>ToS Gating]
        end

        subgraph Sources["Source Tiers"]
            T0[(Tier 0: Free<br/>WikiTree, FindAGrave<br/>NARA, FreeBMD)]
            T1[(Tier 1: Auth Required<br/>FamilySearch<br/>Chronicling America)]
            T2[(Tier 2: Paid<br/>Ancestry<br/>MyHeritage)]
        end

        subgraph Outputs
            LOG[(Research Log<br/>Audit Trail)]
            KG[(JSON-LD<br/>Knowledge Graph)]
        end
    end

    Q --> LEAD
    SEED --> LEAD
    LEAD <--> FQ
    LEAD <--> STATE
    LEAD --> SCOUT
    LEAD --> ANALYST
    SCOUT --> ANALYST
    ANALYST --> LEAD
    CENSOR -.-> SCOUT
    CENSOR -.-> ANALYST
    CENSOR -.-> KG
    SCOUT --> T0
    SCOUT --> T1
    SCOUT --> T2
    STATE --> KG
    LEAD --> LOG
```

## Agent Responsibilities

### 1. The Lead (Orchestrator)

```mermaid
stateDiagram-v2
    [*] --> ReceiveQuery
    ReceiveQuery --> DecomposeTask
    DecomposeTask --> PopulateFrontier
    PopulateFrontier --> SelectNextTask
    SelectNextTask --> DelegateToAgent
    DelegateToAgent --> AwaitResult
    AwaitResult --> UpdateState
    UpdateState --> CheckTermination
    CheckTermination --> SelectNextTask: Continue
    CheckTermination --> GenerateOutput: Done
    GenerateOutput --> [*]
```

**Responsibilities:**
- Task decomposition: Breaks research queries into atomic tasks
- State management: Maintains the evolving knowledge graph
- Priority queue management: Orders tasks by expected information gain
- Termination detection: Recognizes when research goals are met

### 2. The Scout (Tool Specialist)

```mermaid
flowchart LR
    subgraph Scout["The Scout"]
        TASK[Task] --> CLASSIFY{Classify<br/>Source Tier}
        CLASSIFY -->|Tier 0| T0_EXEC[Execute Free]
        CLASSIFY -->|Tier 1| T1_CHECK{Auth<br/>Available?}
        CLASSIFY -->|Tier 2| T2_CHECK{Subscription<br/>Active?}
        T1_CHECK -->|Yes| T1_EXEC[Execute Auth]
        T1_CHECK -->|No| T1_SKIP[Skip + Log]
        T2_CHECK -->|Yes| T2_EXEC[Execute Paid]
        T2_CHECK -->|No| T2_SKIP[Skip + Log]
        T0_EXEC --> EXTRACT[Extract Data]
        T1_EXEC --> EXTRACT
        T2_EXEC --> EXTRACT
        EXTRACT --> NORMALIZE[Normalize]
        NORMALIZE --> RETURN[Return Records]
    end
```

**Tools Available:**
- `search_source(source, query)` - Search a genealogical source
- `browse_record(url)` - Navigate to and parse a record
- `scrape_document(url, selectors)` - Extract structured data
- `fetch_image(url)` - Retrieve document images
- `ocr_document(image)` - Extract text from images

### 3. The Analyst (Intelligence)

```mermaid
flowchart TB
    subgraph Analyst["The Analyst"]
        INPUT[New Records] --> EXTRACT_ENTITIES[Extract Entities<br/>Names, Dates, Places]
        EXTRACT_ENTITIES --> MATCH{Match to<br/>Known Persons?}
        MATCH -->|Yes| MERGE[Merge Evidence]
        MATCH -->|No| CREATE[Create Hypothesis]
        MERGE --> CONFLICT{Conflicts?}
        CONFLICT -->|Yes| RESOLVE[Resolve Conflicts<br/>Weight Evidence]
        CONFLICT -->|No| UPDATE[Update Graph]
        RESOLVE --> UPDATE
        CREATE --> GENERATE[Generate ClueHypothesis]
        GENERATE --> PRIORITIZE[Prioritize by<br/>Information Gain]
        PRIORITIZE --> EMIT[Emit to FrontierQueue]
        UPDATE --> EMIT
    end
```

**Clue Generation Logic:**
- New name discovered → Generate "Find vital records for {name}" hypothesis
- New location discovered → Generate "Search {location} records" hypothesis
- Date range identified → Generate "Search {year} census" hypothesis
- Relationship implied → Generate "Verify {relationship}" hypothesis

### 4. The Censor (Compliance)

```mermaid
flowchart TB
    subgraph Censor["The Censor"]
        INPUT[Data/Request] --> TYPE{Check Type}
        TYPE -->|Source Access| TOS[ToS Compliance]
        TYPE -->|Data Output| PII[PII Scan]
        TYPE -->|Record Store| CONSENT[Consent Check]

        TOS --> TOS_CHECK{Allowed?}
        TOS_CHECK -->|Yes| PASS1[✓ Pass]
        TOS_CHECK -->|No| BLOCK1[✗ Block + Log]

        PII --> PII_CHECK{Contains<br/>Living PII?}
        PII_CHECK -->|No| PASS2[✓ Pass]
        PII_CHECK -->|Yes| REDACT[Redact/Anonymize]
        REDACT --> PASS2

        CONSENT --> CONSENT_CHECK{User<br/>Authorized?}
        CONSENT_CHECK -->|Yes| PASS3[✓ Pass]
        CONSENT_CHECK -->|No| BLOCK3[✗ Block + Log]
    end
```

**Compliance Rules:**
- No scraping sources that prohibit it in ToS
- Redact SSNs, living person addresses, etc.
- Rate limit requests per source
- Log all compliance decisions

## Data Flow: Plan-and-Execute Loop

```mermaid
sequenceDiagram
    participant User
    participant Lead
    participant FrontierQueue
    participant Scout
    participant Analyst
    participant Censor
    participant KnowledgeGraph

    User->>Lead: Research Query + Seed Person
    Lead->>Lead: Decompose into initial tasks
    Lead->>FrontierQueue: Populate initial tasks

    loop Autonomous Planning Loop
        Lead->>FrontierQueue: Get highest priority task
        FrontierQueue-->>Lead: Next task

        alt Search Task
            Lead->>Censor: Check source permissions
            Censor-->>Lead: Approved/Denied
            Lead->>Scout: Execute search
            Scout->>Scout: Search/Browse/Scrape
            Scout-->>Lead: Raw records
        else Analysis Task
            Lead->>Analyst: Analyze records
            Analyst->>Analyst: Extract entities
            Analyst->>Analyst: Generate ClueHypotheses
            Analyst-->>Lead: Hypotheses + Updates
        end

        Lead->>KnowledgeGraph: Update state
        Lead->>FrontierQueue: Add new tasks from hypotheses

        Lead->>Lead: Check termination conditions
    end

    Lead->>Censor: Validate final output
    Censor->>Censor: Redact PII
    Censor-->>Lead: Sanitized graph
    Lead->>User: JSON-LD Knowledge Graph
```

## Source Tier System

```mermaid
flowchart TB
    subgraph "Tier 0: Free, No Auth"
        T0A[WikiTree API]
        T0B[FindAGrave]
        T0C[NARA Catalog]
        T0D[FreeBMD]
        T0E[Chronicling America]
        T0F[BillionGraves]
    end

    subgraph "Tier 1: Free, Auth Required"
        T1A[FamilySearch]
        T1B[Ancestry Free Collections]
        T1C[MyHeritage Free]
    end

    subgraph "Tier 2: Paid Subscription"
        T2A[Ancestry.com]
        T2B[MyHeritage Premium]
        T2C[Newspapers.com]
        T2D[Fold3]
    end

    GATE[Permission Gate] --> T0A & T0B & T0C & T0D & T0E & T0F
    GATE -->|Auth Token| T1A & T1B & T1C
    GATE -->|Subscription| T2A & T2B & T2C & T2D
```

## Research Log Structure

```mermaid
erDiagram
    RESEARCH_SESSION ||--o{ LOG_ENTRY : contains
    LOG_ENTRY ||--o{ SOURCE_ACCESS : records
    LOG_ENTRY ||--o{ DECISION : records
    LOG_ENTRY ||--o{ HYPOTHESIS : generates

    RESEARCH_SESSION {
        uuid session_id
        datetime started_at
        datetime ended_at
        string query
        json seed_person
        string status
    }

    LOG_ENTRY {
        uuid entry_id
        datetime timestamp
        string agent_name
        string action_type
        json context
        string rationale
    }

    SOURCE_ACCESS {
        uuid access_id
        string source_name
        int tier
        string url
        boolean success
        string failure_reason
        int response_time_ms
    }

    DECISION {
        uuid decision_id
        string decision_type
        json options_considered
        string chosen_option
        string rationale
        float confidence
    }

    HYPOTHESIS {
        uuid hypothesis_id
        string hypothesis_type
        string statement
        float priority_score
        string status
        json evidence
    }
```

## JSON-LD Knowledge Graph Output

```mermaid
graph TB
    subgraph "schema.org/Person Graph"
        P1[Person: Subject]
        P2[Person: Father]
        P3[Person: Mother]
        P4[Person: Spouse]
        P5[Person: Child]

        E1[Event: Birth]
        E2[Event: Death]
        E3[Event: Marriage]

        PL1[Place: BirthPlace]
        PL2[Place: DeathPlace]

        S1[Source: Census]
        S2[Source: VitalRecord]
    end

    P1 -->|parent| P2
    P1 -->|parent| P3
    P1 -->|spouse| P4
    P1 -->|children| P5
    P1 -->|birthEvent| E1
    P1 -->|deathEvent| E2
    P1 -->|marriageEvent| E3
    E1 -->|location| PL1
    E2 -->|location| PL2
    E1 -->|source| S1
    E2 -->|source| S2
```

## Termination Conditions

The Lead agent terminates the research loop when ANY of these conditions are met:

1. **Goal Achieved**: All research questions answered with sufficient evidence
2. **Exhaustion**: FrontierQueue is empty (no more hypotheses to explore)
3. **Budget Exceeded**: Maximum API calls or time limit reached
4. **GPS Satisfied**: Primary + corroborating secondary sources found for all claims
5. **User Interrupt**: Manual stop requested

## Error Handling

```mermaid
flowchart TB
    ERROR[Error Occurs] --> TYPE{Error Type}
    TYPE -->|Rate Limit| BACKOFF[Exponential Backoff]
    TYPE -->|Auth Failure| REFRESH[Refresh Token / Skip]
    TYPE -->|Parse Error| LOG_SKIP[Log + Continue]
    TYPE -->|Network Error| RETRY[Retry with Backoff]
    TYPE -->|Source Down| CIRCUIT[Circuit Breaker]

    BACKOFF --> RETRY_LATER[Retry Later]
    REFRESH --> CONTINUE[Continue]
    LOG_SKIP --> CONTINUE
    RETRY --> CONTINUE
    CIRCUIT --> MARK_UNAVAILABLE[Mark Source Unavailable]
    MARK_UNAVAILABLE --> CONTINUE
```

## Formal Specification (Z Notation)

The following Z notation specification serves as the **source of truth** for the Ancestry Engine business logic.

### Basic Types

```
[NAME]          -- Set of all person names
[DATE]          -- Set of all dates
[PLACE]         -- Set of all place identifiers
[URL]           -- Set of all URLs
[UUID]          -- Set of all unique identifiers
[TEXT]          -- Set of all text strings

TIER ::= Tier0 | Tier1 | Tier2

AGENT ::= Lead | Scout | Analyst | Censor

TASK_TYPE ::= SearchTask | AnalyzeTask | VerifyTask | ResolveTask

HYPOTHESIS_STATUS ::= Pending | InProgress | Completed | Rejected

DECISION ::= Accept | Reject | Defer

EVIDENCE_TYPE ::= Primary | Secondary | Authored
```

### Person Schema

```
┌─ Person ─────────────────────────────────────────────┐
│ id : UUID                                            │
│ givenName : NAME                                     │
│ surname : NAME                                       │
│ birthDate : ℙ DATE                                   │
│ deathDate : ℙ DATE                                   │
│ birthPlace : ℙ PLACE                                 │
│ deathPlace : ℙ PLACE                                 │
│ parents : ℙ UUID                                     │
│ spouses : ℙ UUID                                     │
│ children : ℙ UUID                                    │
│ sources : ℙ SourceCitation                           │
├──────────────────────────────────────────────────────┤
│ #parents ≤ 2                                         │
│ id ∉ parents ∪ spouses ∪ children                   │
└──────────────────────────────────────────────────────┘
```

### Source Citation Schema

```
┌─ SourceCitation ─────────────────────────────────────┐
│ id : UUID                                            │
│ repository : TEXT                                    │
│ tier : TIER                                          │
│ url : URL                                            │
│ accessedAt : DATE                                    │
│ evidenceType : EVIDENCE_TYPE                         │
│ originalText : ℙ TEXT                                │
│ confidence : ℝ                                       │
├──────────────────────────────────────────────────────┤
│ 0 ≤ confidence ≤ 1                                   │
└──────────────────────────────────────────────────────┘
```

### Clue Hypothesis Schema

```
┌─ ClueHypothesis ──────────────────────────────────────┐
│ id : UUID                                             │
│ statement : TEXT                                      │
│ targetPerson : ℙ UUID                                 │
│ suggestedSources : ℙ TEXT                             │
│ priority : ℝ                                          │
│ status : HYPOTHESIS_STATUS                            │
│ generatedBy : AGENT                                   │
│ evidence : ℙ SourceCitation                           │
├───────────────────────────────────────────────────────┤
│ 0 ≤ priority ≤ 1                                      │
│ generatedBy = Analyst                                 │
└───────────────────────────────────────────────────────┘
```

### Task Schema

```
┌─ Task ────────────────────────────────────────────────┐
│ id : UUID                                             │
│ taskType : TASK_TYPE                                  │
│ priority : ℝ                                          │
│ assignedTo : ℙ AGENT                                  │
│ hypothesis : ℙ ClueHypothesis                         │
│ sourceConstraint : ℙ TIER                             │
│ completed : 𝔹                                         │
├───────────────────────────────────────────────────────┤
│ 0 ≤ priority ≤ 1                                      │
│ taskType = SearchTask ⇒ assignedTo = {Scout}          │
│ taskType = AnalyzeTask ⇒ assignedTo = {Analyst}       │
└───────────────────────────────────────────────────────┘
```

### System State Schema

```
┌─ AncestryEngineState ─────────────────────────────────┐
│ knowledgeGraph : UUID ⇸ Person                        │
│ frontierQueue : seq Task                              │
│ completedTasks : ℙ Task                               │
│ hypotheses : ℙ ClueHypothesis                         │
│ researchLog : seq LogEntry                            │
│ sourcePermissions : TIER → 𝔹                          │
│ activeAgent : ℙ AGENT                                 │
│ terminated : 𝔹                                        │
├───────────────────────────────────────────────────────┤
│ ∀ t : ran frontierQueue • ¬ t.completed               │
│ ∀ t : completedTasks • t.completed                    │
│ sourcePermissions(Tier0) = true                       │
│ terminated ⇒ frontierQueue = ⟨⟩                       │
└───────────────────────────────────────────────────────┘
```

### Initial State

```
┌─ InitAncestryEngine ──────────────────────────────────┐
│ AncestryEngineState'                                  │
│ seedPerson? : Person                                  │
│ query? : TEXT                                         │
├───────────────────────────────────────────────────────┤
│ knowledgeGraph' = {seedPerson?.id ↦ seedPerson?}     │
│ frontierQueue' = ⟨initialTask(seedPerson?, query?)⟩   │
│ completedTasks' = ∅                                   │
│ hypotheses' = ∅                                       │
│ researchLog' = ⟨⟩                                     │
│ sourcePermissions' = {Tier0 ↦ true, Tier1 ↦ ?, Tier2 ↦ ?} │
│ activeAgent' = ∅                                      │
│ terminated' = false                                   │
└───────────────────────────────────────────────────────┘
```

### The Lead: Task Selection Operation

```
┌─ LeadSelectTask ──────────────────────────────────────┐
│ ΔAncestryEngineState                                  │
│ selectedTask! : Task                                  │
├───────────────────────────────────────────────────────┤
│ ¬ terminated                                          │
│ frontierQueue ≠ ⟨⟩                                    │
│ selectedTask! = head(sortByPriority(frontierQueue))   │
│ frontierQueue' = tail(sortByPriority(frontierQueue))  │
│ activeAgent' = selectedTask!.assignedTo               │
│ researchLog' = researchLog ⁀ ⟨taskSelectionEntry(selectedTask!)⟩ │
└───────────────────────────────────────────────────────┘

── Priority ordering predicate
sortByPriority : seq Task → seq Task
∀ s : seq Task •
  ∀ i, j : dom s • i < j ⇒ (sortByPriority(s))(i).priority ≥ (sortByPriority(s))(j).priority
```

### The Scout: Source Access Operation

```
┌─ ScoutSearchSource ───────────────────────────────────┐
│ ΔAncestryEngineState                                  │
│ task? : Task                                          │
│ records! : ℙ RawRecord                                │
├───────────────────────────────────────────────────────┤
│ Scout ∈ activeAgent                                   │
│ task?.taskType = SearchTask                           │
│                                                       │
│ ── Permission check (gating)                          │
│ ∀ tier : task?.sourceConstraint •                     │
│   sourcePermissions(tier) = true                      │
│                                                       │
│ ── Execute search within permitted tiers              │
│ records! = executeSearch(task?, sourcePermissions)    │
│                                                       │
│ ── Log the access                                     │
│ researchLog' = researchLog ⁀ ⟨sourceAccessEntry(task?, records!)⟩ │
│ activeAgent' = ∅                                      │
└───────────────────────────────────────────────────────┘

── Permission gating predicate
┌─ SourcePermissionGate ────────────────────────────────┐
│ tier? : TIER                                          │
│ allowed! : 𝔹                                          │
│ sourcePermissions : TIER → 𝔹                          │
├───────────────────────────────────────────────────────┤
│ allowed! = sourcePermissions(tier?)                   │
│ tier? = Tier0 ⇒ allowed! = true                       │
└───────────────────────────────────────────────────────┘
```

### The Analyst: Hypothesis Generation Operation

```
┌─ AnalystGenerateHypotheses ───────────────────────────┐
│ ΔAncestryEngineState                                  │
│ records? : ℙ RawRecord                                │
│ newHypotheses! : ℙ ClueHypothesis                     │
├───────────────────────────────────────────────────────┤
│ Analyst ∈ activeAgent                                 │
│                                                       │
│ ── Extract entities from records                      │
│ let entities == extractEntities(records?)             │
│                                                       │
│ ── Generate hypotheses for new names                  │
│ let nameHypotheses == {h : ClueHypothesis |           │
│   ∃ n : entities.names • n ∉ dom knowledgeGraph •     │
│   h.statement = "Find vital records for " ⁀ n ∧       │
│   h.priority = calculatePriority(n, knowledgeGraph)}  │
│                                                       │
│ ── Generate hypotheses for new locations              │
│ let placeHypotheses == {h : ClueHypothesis |          │
│   ∃ p : entities.places •                             │
│   h.statement = "Search records in " ⁀ p ∧           │
│   h.priority = calculatePriority(p, knowledgeGraph)}  │
│                                                       │
│ newHypotheses! = nameHypotheses ∪ placeHypotheses     │
│ hypotheses' = hypotheses ∪ newHypotheses!             │
│                                                       │
│ ── Add new tasks to frontier                          │
│ frontierQueue' = frontierQueue ⁀ hypothesesToTasks(newHypotheses!) │
│                                                       │
│ ── Log rationale                                      │
│ researchLog' = researchLog ⁀ ⟨hypothesisEntry(newHypotheses!)⟩ │
└───────────────────────────────────────────────────────┘

── Priority calculation based on information gain
calculatePriority : (NAME ∪ PLACE) × (UUID ⇸ Person) → ℝ
∀ e : NAME ∪ PLACE; g : UUID ⇸ Person •
  calculatePriority(e, g) =
    let existingEvidence == countEvidence(e, g) in
    1 - (existingEvidence / (existingEvidence + 1))
```

### The Analyst: Conflict Resolution Operation

```
┌─ AnalystResolveConflict ──────────────────────────────┐
│ ΔAncestryEngineState                                  │
│ person? : Person                                      │
│ conflictingClaims? : ℙ (TEXT × SourceCitation)        │
│ resolution! : TEXT × SourceCitation                   │
├───────────────────────────────────────────────────────┤
│ Analyst ∈ activeAgent                                 │
│ #conflictingClaims? ≥ 2                               │
│                                                       │
│ ── Weight by evidence type and source tier            │
│ let weights == {(claim, src) : conflictingClaims? •   │
│   evidenceWeight(src.evidenceType) ×                  │
│   tierWeight(src.tier) ×                              │
│   src.confidence}                                     │
│                                                       │
│ ── Select highest weighted claim                      │
│ resolution! = argmax(weights)                         │
│                                                       │
│ ── Update knowledge graph                             │
│ knowledgeGraph' = knowledgeGraph ⊕                    │
│   {person?.id ↦ applyResolution(person?, resolution!)}│
│                                                       │
│ ── Log resolution rationale                           │
│ researchLog' = researchLog ⁀                          │
│   ⟨conflictResolutionEntry(conflictingClaims?, resolution!)⟩ │
└───────────────────────────────────────────────────────┘

── Evidence weight function
evidenceWeight : EVIDENCE_TYPE → ℝ
evidenceWeight(Primary) = 1.0
evidenceWeight(Secondary) = 0.7
evidenceWeight(Authored) = 0.4

── Tier weight function
tierWeight : TIER → ℝ
tierWeight(Tier0) = 0.8
tierWeight(Tier1) = 0.9
tierWeight(Tier2) = 1.0
```

### The Censor: PII Compliance Operation

```
┌─ CensorValidateOutput ────────────────────────────────┐
│ ΞAncestryEngineState                                  │
│ data? : Person                                        │
│ sanitized! : Person                                   │
│ violations! : ℙ TEXT                                  │
├───────────────────────────────────────────────────────┤
│ Censor ∈ activeAgent                                  │
│                                                       │
│ ── Check for living person (born < 100 years ago, no death) │
│ let isLiving == data?.birthDate ≠ ∅ ∧                 │
│   max(data?.birthDate) > currentYear - 100 ∧         │
│   data?.deathDate = ∅                                 │
│                                                       │
│ ── Redact if living                                   │
│ isLiving ⇒                                            │
│   sanitized! = redactLivingPII(data?) ∧               │
│   violations! = {"Living person PII redacted"}        │
│                                                       │
│ ¬isLiving ⇒                                           │
│   sanitized! = data? ∧                                │
│   violations! = ∅                                     │
└───────────────────────────────────────────────────────┘

── PII redaction function
redactLivingPII : Person → Person
∀ p : Person •
  redactLivingPII(p) = p ⊕ {
    birthDate ↦ {approximateDecade(max(p.birthDate))},
    birthPlace ↦ {generalizePlace(head(p.birthPlace))}
  }
```

### The Censor: ToS Compliance Gate

```
┌─ CensorCheckSourceAccess ─────────────────────────────┐
│ ΞAncestryEngineState                                  │
│ source? : TEXT                                        │
│ action? : TEXT                                        │
│ allowed! : 𝔹                                          │
│ reason! : TEXT                                        │
├───────────────────────────────────────────────────────┤
│ Censor ∈ activeAgent                                  │
│                                                       │
│ let tosRules == loadToSRules(source?)                 │
│                                                       │
│ ── Check if action is permitted                       │
│ action? ∈ tosRules.allowedActions ⇒                   │
│   allowed! = true ∧ reason! = "Action permitted"      │
│                                                       │
│ action? ∈ tosRules.prohibitedActions ⇒                │
│   allowed! = false ∧                                  │
│   reason! = "Action prohibited by ToS: " ⁀ source?    │
│                                                       │
│ ── Log compliance decision                            │
│ researchLog' = researchLog ⁀                          │
│   ⟨complianceEntry(source?, action?, allowed!, reason!)⟩ │
└───────────────────────────────────────────────────────┘
```

### Plan-and-Execute Loop

```
┌─ PlanAndExecuteLoop ──────────────────────────────────┐
│ ΔAncestryEngineState                                  │
├───────────────────────────────────────────────────────┤
│ ── Loop invariant                                     │
│ ¬ terminated ∧ frontierQueue ≠ ⟨⟩                     │
│                                                       │
│ ── Loop body (one iteration)                          │
│ LeadSelectTask ;                                      │
│ (ScoutSearchSource ∨ AnalystGenerateHypotheses) ;     │
│ CensorValidateOutput ;                                │
│ LeadUpdateState ;                                     │
│ LeadCheckTermination                                  │
└───────────────────────────────────────────────────────┘

┌─ LeadCheckTermination ────────────────────────────────┐
│ ΔAncestryEngineState                                  │
├───────────────────────────────────────────────────────┤
│ ── Termination conditions                             │
│ let goalAchieved == checkGoalSatisfied(knowledgeGraph)│
│ let exhausted == frontierQueue = ⟨⟩ ∧ hypotheses = ∅  │
│ let budgetExceeded == #researchLog > maxLogEntries    │
│ let gpsSatisfied == checkGPSCoverage(knowledgeGraph)  │
│                                                       │
│ terminated' = goalAchieved ∨ exhausted ∨              │
│               budgetExceeded ∨ gpsSatisfied           │
│                                                       │
│ terminated' ⇒                                         │
│   researchLog' = researchLog ⁀ ⟨terminationEntry(     │
│     goalAchieved, exhausted, budgetExceeded, gpsSatisfied)⟩ │
└───────────────────────────────────────────────────────┘

── GPS coverage check (primary + secondary for each claim)
checkGPSCoverage : (UUID ⇸ Person) → 𝔹
∀ g : UUID ⇸ Person •
  checkGPSCoverage(g) =
    ∀ p : ran g •
      ∃ s1, s2 : p.sources •
        s1.evidenceType = Primary ∧
        s2.evidenceType = Secondary ∧
        s1 ≠ s2
```

### Research Log Entry Schema

```
┌─ LogEntry ────────────────────────────────────────────┐
│ id : UUID                                             │
│ timestamp : DATE                                      │
│ agent : AGENT                                         │
│ actionType : TEXT                                     │
│ rationale : TEXT                                      │
│ context : TEXT                                        │
│ revisitReason : ℙ TEXT                                │
├───────────────────────────────────────────────────────┤
│ ── Revisit logging requirement                        │
│ actionType = "revisit" ⇒ revisitReason ≠ ∅           │
└───────────────────────────────────────────────────────┘
```

### Revisit Source Operation

```
┌─ ScoutRevisitSource ──────────────────────────────────┐
│ ΔAncestryEngineState                                  │
│ source? : TEXT                                        │
│ previousAccess? : LogEntry                            │
│ reason? : TEXT                                        │
├───────────────────────────────────────────────────────┤
│ Scout ∈ activeAgent                                   │
│                                                       │
│ ── Must have previous access to this source           │
│ ∃ entry : ran researchLog •                           │
│   entry.actionType = "source_access" ∧                │
│   entry.context = source?                             │
│                                                       │
│ ── Must provide rationale for revisit                 │
│ reason? ∈ {                                           │
│   "New hypothesis requires additional data",          │
│   "Previous search parameters too narrow",            │
│   "Conflict resolution requires corroboration",       │
│   "Time-based record update check"                    │
│ }                                                     │
│                                                       │
│ ── Log revisit with rationale                         │
│ researchLog' = researchLog ⁀ ⟨(                       │
│   id ↦ newUUID(),                                     │
│   timestamp ↦ now(),                                  │
│   agent ↦ Scout,                                      │
│   actionType ↦ "revisit",                             │
│   rationale ↦ reason?,                                │
│   context ↦ source?,                                  │
│   revisitReason ↦ {reason?}                           │
│ )⟩                                                    │
└───────────────────────────────────────────────────────┘
```

### System Invariants

```
── Global system invariants that must hold at all times

Invariant1: ∀ s : AncestryEngineState •
  ∀ p : ran s.knowledgeGraph •
    p.id ∉ p.parents ∪ p.spouses ∪ p.children
    -- A person cannot be their own relative

Invariant2: ∀ s : AncestryEngineState •
  s.sourcePermissions(Tier0) = true
    -- Tier 0 sources are always accessible

Invariant3: ∀ s : AncestryEngineState •
  s.terminated ⇒ s.frontierQueue = ⟨⟩
    -- Terminated state has empty queue

Invariant4: ∀ s : AncestryEngineState •
  ∀ t : ran s.frontierQueue • ¬ t.completed
    -- Frontier only contains incomplete tasks

Invariant5: ∀ s : AncestryEngineState •
  ∀ entry : ran s.researchLog •
    entry.actionType = "revisit" ⇒ entry.revisitReason ≠ ∅
    -- All revisits must have documented rationale

Invariant6: ∀ s : AncestryEngineState •
  ∀ h : s.hypotheses •
    h.generatedBy = Analyst
    -- Only Analyst generates hypotheses
```

---

## Implementation Stack

- **Orchestration**: LangGraph for stateful agent coordination
- **Models**: Pydantic v2 for data validation
- **LLM**: Claude/GPT-4 for reasoning tasks
- **Storage**: SQLite for research log, ChromaDB for semantic search
- **Output**: JSON-LD compatible with schema.org vocabulary
