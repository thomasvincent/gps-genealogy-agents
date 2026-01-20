from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gps_agents.fs import atomic_write


@dataclass
class WikiPlanBundle:
    run_id: str
    dir: Path
    plan_json: Path
    summary_md: Path


@dataclass
class WikiBundle:
    run_id: str
    dir: Path
    plan_json: Path
    summary_md: Path
    facts_json: Path
    review_json: Path
    wikidata_payload_json: Path
    wikipedia_md: Path
    wikitree_md: Path
    wikitree_yaml: Path
    gedcom_file: Path


def write_plan_bundle(
    base_dir: Path | str,
    run_id: str,
    subject: str,
    plan: dict[str, Any],
) -> WikiPlanBundle:
    base = Path(base_dir) / run_id
    base.mkdir(parents=True, exist_ok=True)

    plan_path = base / "plan.json"
    summary_path = base / "SUMMARY.md"

    # Keep deterministic: do not include timestamps
    atomic_write(plan_path, json.dumps({
        "run_id": run_id,
        "subject": subject,
        "plan": plan,
    }, indent=2, default=str).encode("utf-8"))

    # Write summary markdown (deterministic)
    summary = [
        f"# Wiki Plan (Run {run_id})",
        "",
        f"Subject: **{subject}**",
        "",
        "This bundle was generated in dry-run mode and must be reviewed and approved before any publishing.",
        "Place an `approved.yaml` with `approved: true` and a `reviewer:` field in this directory to signal approval.",
    ]
    atomic_write(summary_path, "\n".join(summary).encode("utf-8"))

    return WikiPlanBundle(run_id=run_id, dir=base, plan_json=plan_path, summary_md=summary_path)


def write_wiki_bundle(
    base_dir: Path | str,
    run_id: str,
    subject: str,
    artifacts: dict[str, Any],
) -> WikiBundle:
    """Write the full wiki artifact bundle deterministically.

    Files written:
      - plan.json, SUMMARY.md
      - facts.json, review.json, wikidata_payload.json
      - wikipedia_draft.md, wikitree_bio.md, wikitree_profile.yaml
      - subject.ged
    """
    base = Path(base_dir) / run_id
    base.mkdir(parents=True, exist_ok=True)

    # Validate JSON shapes if schemas present (optional dependency: jsonschema)
    try:
        from jsonschema import validate  # type: ignore
        import json as _json
        facts_schema = _json.loads((Path("schemas/wiki_facts.schema.json")).read_text())
        review_schema = _json.loads((Path("schemas/wiki_review.schema.json")).read_text())
        payload_schema = _json.loads((Path("schemas/wikidata_payload.schema.json")).read_text())
        validate(artifacts.get("facts", []), facts_schema)
        validate(artifacts.get("review", {}), review_schema)
        validate(artifacts.get("wikidata_payload", {}), payload_schema)
    except Exception:
        # Best-effort: do not block writes if schemas or lib missing
        pass

    plan_path = base / "plan.json"
    summary_path = base / "SUMMARY.md"
    facts_path = base / "facts.json"
    review_path = base / "review.json"
    payload_path = base / "wikidata_payload.json"
    wikipedia_path = base / "wikipedia_draft.md"
    wikitree_path = base / "wikitree_bio.md"
    wikitree_yaml = base / "wikitree_profile.yaml"
    gedcom_path = base / "subject.ged"

    # Deterministic JSON/text writes
    atomic_write(plan_path, json.dumps({
        "run_id": run_id,
        "subject": subject,
        "plan": {
            "engine": "sk",
            "outputs": [
                "facts.json", "review.json", "wikidata_payload.json",
                "wikipedia_draft.md", "wikitree_bio.md", "wikitree_profile.yaml", "subject.ged",
            ],
        },
    }, indent=2, default=str).encode("utf-8"))

    summary = [
        f"# Wiki Bundle (Run {run_id})",
        "",
        f"Subject: **{subject}**",
        "",
        "Artifacts:",
        "- facts.json",
        "- review.json",
        "- wikidata_payload.json",
        "- wikipedia_draft.md",
        "- wikitree_bio.md",
        "- wikitree_profile.yaml",
        "- subject.ged",
        "",
        "Approval required before apply. Create approved.yaml with approved: true and reviewer: ...",
    ]
    atomic_write(summary_path, "\n".join(summary).encode("utf-8"))

    atomic_write(facts_path, json.dumps(artifacts.get("facts", []), indent=2, default=str).encode("utf-8"))
    atomic_write(review_path, json.dumps(artifacts.get("review", {}), indent=2, default=str).encode("utf-8"))
    atomic_write(payload_path, json.dumps(artifacts.get("wikidata_payload", {}), indent=2, default=str).encode("utf-8"))

    atomic_write(wikipedia_path, (artifacts.get("wikipedia_draft", "")).encode("utf-8"))
    atomic_write(wikitree_path, (artifacts.get("wikitree_bio", "")).encode("utf-8"))

    # YAML profile if present
    try:
        import yaml  # type: ignore
        profile = artifacts.get("wikitree_profile", {})
        atomic_write(wikitree_yaml, yaml.safe_dump(profile, sort_keys=True).encode("utf-8"))
    except Exception:
        # Fallback: write JSON as YAML placeholder
        atomic_write(wikitree_yaml, json.dumps(artifacts.get("wikitree_profile", {}), indent=2).encode("utf-8"))

    # GEDCOM
    gedcom_text = artifacts.get("gedcom") or ""
    atomic_write(gedcom_path, gedcom_text.encode("utf-8"))

    return WikiBundle(
        run_id=run_id,
        dir=base,
        plan_json=plan_path,
        summary_md=summary_path,
        facts_json=facts_path,
        review_json=review_path,
        wikidata_payload_json=payload_path,
        wikipedia_md=wikipedia_path,
        wikitree_md=wikitree_path,
        wikitree_yaml=wikitree_yaml,
        gedcom_file=gedcom_path,
    )

