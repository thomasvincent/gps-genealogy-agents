# Idempotency Policy

This document summarizes the idempotency rules implemented in gps-genealogy-agents.

## Fingerprints
- Deterministic, stable across reruns
- Entities: Person, Event, Source, Citation, Place, Relationship, Media
- Normalization: NFKD diacritics strip, casefold, whitespace collapse, punctuation removal
- Dates: reduced to coarsest reliable precision; approximate/before/after → year-only
- Exclude volatile fields (e.g., accessed_at)

## Upserts (MATCH → MERGE)
1. O(1) lookup by fingerprint in `fingerprint_index`
2. If not found, run matcher fallback (Person only)
   - Auto-merge when `merge_threshold` (default 0.95)
   - 0.80–0.95 raises `IdempotencyBlock` for human review
3. Otherwise, create and record fingerprint

## Concurrency Safety
- SQLite `BEGIN IMMEDIATE` transaction
- Reservation-and-claim on `fingerprint_index`:
  - ensure row (NULL handle) → create record → claim handle
  - if claim fails, reuse winner
- `busy_timeout=5000` to smooth contention
- Fallback lock table for rare contention paths

## Timeline Guards
- Death before birth → block
- Event after death → block
- Lifespan > `max_lifespan` (default 120) → block
- Marriage before age `min_parent_age` (default 12) → block

## Wikidata Statement Idempotency
- `ensure_statement()` adds only if value+qualifiers+references not already present
- Order-independent comparison
- Normalizes times (by precision), quantities (amount/unit), and URLs (host/scheme lowercase, strip UTM, no trailing slash)
- Durable cache of statement fingerprint → GUID in SQLite

## Media
- Content-hash addressed (SHA-256): `root/aa/bb/hash`
- Atomic writes to avoid partial files
- Reuse if file already exists

## Git
- `safe_commit()` compares staged index against HEAD; skips no-op commits

## Config
- `src/gps_agents/idempotency/config.py` with env overrides:
- `IDEMPOTENCY_MERGE_THRESHOLD` (default 0.95)
- `IDEMPOTENCY_REVIEW_LOW` (0.8)
- `IDEMPOTENCY_REVIEW_HIGH` (0.95)
- `IDEMPOTENCY_MIN_PARENT_AGE` (12)
- `IDEMPOTENCY_MAX_PARENT_AGE` (60)
- `IDEMPOTENCY_MAX_LIFESPAN` (120)
- `IDEMPOTENCY_LOCK_TTL` (300)

## Backfill
- `gps-agents backfill idempotency <path-to-gramps-db>` populates fingerprints and mappings for existing data.

## Agentic Wiki Planner (Dry-run)
- `gps-agents wiki plan --subject "Name" --article path/to/text.md [--wikidata-qid Qxxxx] [--wikitree-id ...]`
- Produces structured outputs for Wikipedia/Wikidata/WikiTree without writing.
- Writes must later use ensure_statement() and mapping lookups to avoid duplicates.

## Agentic Wiki End-to-End (deterministic, gated)
- `gps-agents wiki run --subject "Name" --article notes.md [--run-id UUID]`
  - Generates a deterministic bundle under `research/wiki_plans/<RUN_ID>/`:
    - plan.json, SUMMARY.md, facts.json, review.json, wikidata_payload.json
    - wikipedia_draft.md, wikitree_bio.md, wikitree_profile.yaml, subject.ged
  - Commits only when content changes (safe_commit).
- `gps-agents wiki stage --subject "Name" --article notes.md [--engine sk|autogen] [--run-id UUID]`
  - Same artifacts as `wiki run`, useful when using AutoGen engine.
- `gps-agents wiki show --bundle research/wiki_plans/<RUN_ID> [--json]`
  - Summarize/validate a bundle (best-effort JSON Schema validation).
- Approval gate (HARD RULE): No external writes without approval.
  - Create `approved.yaml` in the bundle with:
    - `approved: true`
    - `reviewer: <name>`
- `gps-agents wiki apply --bundle research/wiki_plans/<RUN_ID> --approval approved.yaml [--drafts-root drafts]`
  - Wikidata: Calls `ensure_statement()` per claim (uses durable cache; never invents QIDs; blocks if `entity != Q*`).
  - Wikipedia/WikiTree: Stages drafts in Git only at `drafts/wikipedia/<slug>.md` and `drafts/wikitree/<slug>.md`.
  - Writes `publish.log` JSONL in the bundle (deterministic overwrite) and commits only when changed.

### CI trigger (optional)
- `.github/workflows/wiki-apply.yml` runs `wiki apply` when `research/wiki_plans/**/approved.yaml` is pushed.
- Publishes a summary and uploads `publish.log` as an artifact.
