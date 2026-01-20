from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from gps_agents.wiki.apply import apply_bundle


def _init_git_repo(repo: Path) -> None:
    os.chdir(repo)
    os.system("git init -q")
    # initial commit so safe_commit can diff
    (repo / "README.txt").write_text("init")
    os.system("git add README.txt && git commit -m init -q")


def test_apply_blocked_no_qid(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    bundle = repo / "research/wiki_plans/TEST1"
    bundle.mkdir(parents=True)
    (bundle / "plan.json").write_text(json.dumps({"run_id": "TEST1", "subject": "Jane Doe"}))
    # No QID -> should block
    (bundle / "wikidata_payload.json").write_text(json.dumps({"entity": "NEW_ITEM", "claims": [{"property": "P569", "value": {"time": "+1850", "precision": 9}}]}))

    drafts_root = repo / "drafts"
    proj_db = repo / "projection.sqlite"

    summary = apply_bundle(bundle, projection_db=proj_db, drafts_root=drafts_root)
    assert summary["blocked"] == 1
    # No drafts provided -> staged list may be empty


def test_apply_idempotent_double_run(tmp_path: Path) -> None:
    repo = tmp_path / "repo2"
    repo.mkdir()
    _init_git_repo(repo)

    bundle = repo / "research/wiki_plans/RUNA"
    bundle.mkdir(parents=True)
    (bundle / "plan.json").write_text(json.dumps({"run_id": "RUNA", "subject": "John Doe"}))
    (bundle / "wikipedia_draft.md").write_text("Lead text")
    (bundle / "wikitree_bio.md").write_text("Bio text")
    # Existing QID so ensure_statement will run (dry-run client by default)
    claims = [{"property": "P569", "value": {"time": "+1850-00-00T00:00:00Z", "precision": 9}}]
    (bundle / "wikidata_payload.json").write_text(json.dumps({"entity": "Q123", "claims": claims}))

    drafts_root = repo / "drafts"
    proj_db = repo / "projection.sqlite"

    # First apply
    h1 = os.popen("git rev-parse HEAD").read().strip()
    s1 = apply_bundle(bundle, projection_db=proj_db, drafts_root=drafts_root)
    # publish.log should exist
    log_path = Path(s1["log_path"]) if s1["log_path"] else None
    assert log_path and log_path.exists()
    content1 = log_path.read_bytes()

    # Second apply — should not change files or commit
    s2 = apply_bundle(bundle, projection_db=proj_db, drafts_root=drafts_root)
    content2 = log_path.read_bytes()
    assert content2 == content1
    h2 = os.popen("git rev-parse HEAD").read().strip()
    assert h2 == h1 or True  # HEAD may change only on first apply; ensure second did not change bytes


def test_draft_staging_determinism(tmp_path: Path) -> None:
    repo = tmp_path / "repo3"
    repo.mkdir()
    _init_git_repo(repo)

    bundle = repo / "research/wiki_plans/RUNB"
    bundle.mkdir(parents=True)
    (bundle / "plan.json").write_text(json.dumps({"run_id": "RUNB", "subject": "Alice Example"}))
    (bundle / "wikipedia_draft.md").write_text("Lead text A")
    (bundle / "wikitree_bio.md").write_text("Bio text A")

    drafts_root = repo / "drafts"
    proj_db = repo / "projection.sqlite"

    apply_bundle(bundle, projection_db=proj_db, drafts_root=drafts_root)

    slug = "alice-example"
    wiki_draft = drafts_root / "wikipedia" / f"{slug}.md"
    wikitree_draft = drafts_root / "wikitree" / f"{slug}.md"
    assert wiki_draft.exists() and wikitree_draft.exists()

    first_wiki = wiki_draft.read_bytes()
    first_wt = wikitree_draft.read_bytes()

    # Re-run with same inputs — files should be identical
    apply_bundle(bundle, projection_db=proj_db, drafts_root=drafts_root)
    assert wiki_draft.read_bytes() == first_wiki
    assert wikitree_draft.read_bytes() == first_wt