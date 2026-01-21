from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from gps_agents.cli import app


def _init_git_repo(repo: Path) -> None:
    os.chdir(repo)
    os.system("git init -q")
    # initial commit
    (repo / "README.txt").write_text("init")
    os.system("git add README.txt && git commit -m init -q")


def test_cli_stage_show_and_apply_sk(tmp_path: Path) -> None:
    runner = CliRunner()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    article = repo / "notes.md"
    article.write_text("Some research notes")
    run_id = "RUNCLI"

    # Stage with SK engine
    result_stage = runner.invoke(
        app,
        [
            "wiki", "stage",
            "--subject", "Test Person",
            "--article", str(article),
            "--engine", "sk",
            "--run-id", run_id,
        ],
        env={},
        catch_exceptions=False,
    )
    assert result_stage.exit_code == 0

    bundle_dir = repo / "research/wiki_plans" / run_id
    assert (bundle_dir / "plan.json").exists()
    assert (bundle_dir / "wikidata_payload.json").exists()

    # Patch wikipedia_draft.md to include required quality gate content
    wiki_draft = bundle_dir / "wikipedia_draft.md"
    draft_content = wiki_draft.read_text() if wiki_draft.exists() else ""
    patched_content = f"""# Test Person

{draft_content}

## GPS Grade Card

| Criterion | Score |
|-----------|-------|
| Overall   | 10/10 |

## Research Notes

Test research notes for CI validation.
"""
    wiki_draft.write_text(patched_content)

    # Patch wikidata_payload.json to include required multilingual labels
    wikidata_path = bundle_dir / "wikidata_payload.json"
    wikidata_payload = json.loads(wikidata_path.read_text()) if wikidata_path.exists() else {}
    wikidata_payload["labels"] = {
        "en": "Test Person",
        "es": "Persona de Prueba",
        "fr": "Personne Test",
        "de": "Testperson",
        "it": "Persona Test",
        "nl": "Testpersoon",
    }
    wikidata_payload["descriptions"] = {
        "en": "Test subject for CI",
        "es": "Sujeto de prueba para CI",
        "fr": "Sujet de test pour CI",
        "de": "Testobjekt für CI",
        "it": "Soggetto di prova per CI",
        "nl": "Testonderwerp voor CI",
    }
    wikidata_path.write_text(json.dumps(wikidata_payload, indent=2))

    # Approve and apply
    approved = repo / "approved.yaml"
    approved.write_text("approved: true\nreviewer: CI\n")

    # Show summary before apply
    result_show = runner.invoke(
        app,
        [
            "wiki", "show",
            "--bundle", str(bundle_dir),
            "--json",
        ],
        env={},
        catch_exceptions=False,
    )
    assert result_show.exit_code == 0

    result_apply = runner.invoke(
        app,
        [
            "wiki", "apply",
            "--bundle", str(bundle_dir),
            "--approval", str(approved),
        ],
        env={},
        catch_exceptions=False,
    )
    assert result_apply.exit_code == 0

    # Verify drafts and log
    slug = "test-person"
    assert (repo / "drafts/wikipedia" / f"{slug}.md").exists()
    assert (repo / "drafts/wikitree" / f"{slug}.md").exists()
    assert (bundle_dir / "publish.log").exists()