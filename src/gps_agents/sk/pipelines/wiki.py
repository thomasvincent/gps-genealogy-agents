from __future__ import annotations

from typing import Any


async def plan_wiki_subject(
    *,
    article_text: str,
    subject_name: str,
    kernel_config: Any,
) -> dict[str, Any]:
    """Semantic Kernel-based planner for wiki publishing (dry-run only).

    This is a lightweight orchestrator returning deterministic, structured outputs
    that downstream bundle writers and approvers can review.
    """
    # NOTE: For now, we keep it deterministic/minimal. You can enrich this by invoking
    # SK planners and plugins in src/gps_agents/sk/plugins/* to extract entities,
    # map facts, and draft content.

    wikipedia_draft = f"""== {subject_name} ==\n\nThis is a draft lead for {subject_name}. Sources and verification pending human review."""
    wikitree_bio = f"""Biography for {subject_name}\n\n== Research Notes ==\nGenerated (dry-run)."""

    wikidata_payload = {
        "entity": "NEW_ITEM",
        "labels": {"en": subject_name},
        "claims": [],  # to be filled by SK extractors when available
        "generated_at": "DRY-RUN",
    }

    # Deterministic placeholders for full bundle shape
    facts = []
    review = {"status": "pending", "checks": []}
    wikitree_profile = {"Name": subject_name, "Biography": "Draft pending review."}
    subject_gedcom = f"""0 HEAD\n1 SOUR GPS-Genealogy-Agents\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME {subject_name} /{subject_name.split()[-1] if ' ' in subject_name else subject_name}/\n0 TRLR\n"""

    return {
        "subject": subject_name,
        "wikipedia_draft": wikipedia_draft,
        "wikitree_bio": wikitree_bio,
        "wikidata_payload": wikidata_payload,
        "facts": facts,
        "review": review,
        "wikitree_profile": wikitree_profile,
        "gedcom": subject_gedcom,
        "messages": [
            {"role": "system", "content": "SK wiki planner (dry-run) produced minimal structured outputs."}
        ],
    }
