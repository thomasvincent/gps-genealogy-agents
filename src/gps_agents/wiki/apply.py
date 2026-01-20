from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import structlog

from gps_agents.git_utils import safe_commit
from gps_agents.projections.sqlite_projection import SQLiteProjection
from gps_agents.wikidata.idempotency import ensure_statement

logger = structlog.get_logger(__name__)


@dataclass
class ApplyResult:
    created: int = 0
    exists: int = 0
    skipped: int = 0
    blocked: int = 0
    errors: int = 0


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-") or "subject"


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_jsonl(path: Path, records: Iterable[dict]) -> None:
    """Deterministically write JSONL records (overwrite, stable order) so reruns don't change bytes."""
    lines = [json.dumps(r, separators=(",", ":")) for r in records]
    content = "\n".join(lines) + ("\n" if lines else "")
    # Overwrite atomically
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


class _DryRunWD:
    def get_claims(self, entity_id: str, property_id: str) -> list[dict]:
        return []

    def add_claim(self, entity_id: str, property_id: str, value, qualifiers, references) -> str:
        # Return a pseudo GUID without writing
        return f"{entity_id}$DRYRUN"


def _get_wikidata_client() -> Any:
    # Enable real writes only when explicitly requested
    if os.getenv("WIKIDATA_WRITE") not in {"1", "true", "TRUE"}:
        logger.info("wikidata.client", mode="dry_run")
        return _DryRunWD()
    try:
        import pywikibot  # type: ignore
        from pywikibot import Claim, ItemPage, WbTime

        def _to_pwb_value(repo, val):
            # Minimal mapping: support time dictionaries; pass through others
            if isinstance(val, dict) and "time" in val and isinstance(val.get("time"), str):
                t = val["time"].lstrip("+")
                # Expect formats: YYYY, YYYY-MM, YYYY-MM-DD
                parts = t.split("T")[0].split("-")
                year = int(parts[0]) if parts and parts[0] else None
                month = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                day = int(parts[2]) if len(parts) > 2 and parts[2] else 0
                precision = val.get("precision") or (11 if day else (10 if month else 9))
                try:
                    return WbTime(year=year, month=month or None, day=day or None, precision=precision, site=repo)
                except Exception:
                    return val
            return val

        class PWBClient:
            def __init__(self) -> None:
                self.site = pywikibot.Site("wikidata", "wikidata")
                self.repo = self.site.data_repository()

            def get_claims(self, entity_id: str, property_id: str) -> list[dict]:
                item = ItemPage(self.repo, entity_id)
                item.get()
                claims = []
                for cl in item.claims.get(property_id, []):
                    val = cl.getTarget()
                    # Minimal normalization for comparison; callers perform canonicalization
                    claims.append(
                        {
                            "id": cl.snak,  # not a real GUID; ensure_statement handles GUID extraction
                            "property": property_id,
                            "value": val.toJSON() if hasattr(val, "toJSON") else val,
                            "qualifiers": {q: [qq.getTarget().toJSON() if hasattr(qq.getTarget(), "toJSON") else qq.getTarget() for qq in qs] for q, qs in cl.qualifiers.items()} if cl.qualifiers else {},
                            "references": [ref.toJSON() if hasattr(ref, "toJSON") else {} for ref in cl.sources or []],
                        }
                    )
                return claims

            def add_claim(self, entity_id: str, property_id: str, value, qualifiers, references) -> str:
                item = ItemPage(self.repo, entity_id)
                item.get()
                claim = Claim(self.repo, property_id)
                claim.setTarget(_to_pwb_value(self.repo, value))
                item.addClaim(claim)
                # NOTE: Qualifiers and references are not applied in this minimal integration.
                # Avoid partial/wrong writes until full mapping is implemented.
                logger.info("wikidata.pywikibot_add", entity=entity_id, property=property_id)
                return claim.snak

        logger.info("wikidata.client", mode="pywikibot")
        return PWBClient()
    except Exception as e:  # noqa: BLE001
        logger.warning("wikidata.client_unavailable", error=str(e))
        return _DryRunWD()


def apply_wikidata_from_bundle(bundle_dir: Path, *, projection: SQLiteProjection) -> list[dict]:
    """Apply Wikidata claims from a staged bundle.

    Returns a list of publish log entries (JSON-serializable dicts).
    """
    payload = _load_json(bundle_dir / "wikidata_payload.json")
    plan = _load_json(bundle_dir / "plan.json") or {}
    run_id = plan.get("run_id") or bundle_dir.name

    log_entries: list[dict] = []
    if not payload:
        return log_entries

    entity = payload.get("entity")
    if not isinstance(entity, str) or not entity.upper().startswith("Q"):
        log_entries.append(
            {
                "run_id": run_id,
                "platform": "wikidata",
                "action": "blocked_no_qid",
                "reason": "Payload does not specify existing QID; creation not allowed by policy.",
            }
        )
        return log_entries

    client = _get_wikidata_client()

    claims: list[dict] = payload.get("claims") or []
    for c in claims:
        try:
            prop = c.get("property")
            val = c.get("value")
            qualifiers = c.get("qualifiers")
            references = c.get("references")
            guid = ensure_statement(
                client,
                entity,
                prop,
                val,
                qualifiers=qualifiers,
                references=references,
                projection=projection,
            )
            log_entries.append(
                {
                    "run_id": run_id,
                    "platform": "wikidata",
                    "entity": entity,
                    "property": prop,
                    "guid": guid,
                    "action": "ensured",
                }
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("wikidata.apply_error", property=c.get("property"))
            log_entries.append(
                {
                    "run_id": run_id,
                    "platform": "wikidata",
                    "entity": entity,
                    "property": c.get("property"),
                    "action": "error",
                    "error": str(e),
                }
            )
    return log_entries


def stage_drafts_from_bundle(bundle_dir: Path, drafts_root: Path) -> list[Path]:
    plan = _load_json(bundle_dir / "plan.json") or {}
    subject = plan.get("subject") or bundle_dir.name
    slug = _slug(subject)

    out_files: list[Path] = []
    # Wikipedia
    wiki_src = bundle_dir / "wikipedia_draft.md"
    if wiki_src.exists():
        dst = drafts_root / "wikipedia" / f"{slug}.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(wiki_src.read_text(encoding="utf-8"), encoding="utf-8")
        out_files.append(dst)
    # WikiTree
    wt_src = bundle_dir / "wikitree_bio.md"
    if wt_src.exists():
        dst = drafts_root / "wikitree" / f"{slug}.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(wt_src.read_text(encoding="utf-8"), encoding="utf-8")
        out_files.append(dst)

    return out_files


def apply_bundle(bundle_dir: Path, *, projection_db: Path, drafts_root: Path) -> dict[str, Any]:
    """High-level apply: stage drafts, apply Wikidata (idempotent), and commit changes.

    Returns a summary dict.
    """
    projection = SQLiteProjection(str(projection_db))

    changed_files: list[Path] = []
    # Stage drafts in repo
    staged = stage_drafts_from_bundle(bundle_dir, drafts_root)
    changed_files.extend(staged)

    # Wikidata apply (idempotent)
    log_entries = apply_wikidata_from_bundle(bundle_dir, projection=projection)
    publish_log = bundle_dir / "publish.log"
    if log_entries:
        _write_jsonl(publish_log, log_entries)
        changed_files.append(publish_log)

    # Commit all changed files and approved.yaml if present
    repo = Path.cwd()
    if (bundle_dir / "approved.yaml").exists():
        changed_files.append(bundle_dir / "approved.yaml")

    if changed_files:
        safe_commit(
            repo,
            changed_files,
            "chore(wiki): apply bundle and stage drafts idempotently\n\nCo-Authored-By: Warp <agent@warp.dev>",
        )

    return {
        "staged": [str(p) for p in staged],
        "applied_claims": sum(1 for e in log_entries if e.get("action") == "ensured"),
        "blocked": sum(1 for e in log_entries if e.get("action", "").startswith("blocked")),
        "errors": sum(1 for e in log_entries if e.get("action") == "error"),
        "log_path": str(publish_log) if log_entries else None,
    }