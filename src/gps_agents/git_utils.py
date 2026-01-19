from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Iterable

import structlog

logger = structlog.get_logger(__name__)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _head_file_bytes(repo: Path, relpath: str) -> bytes | None:
    try:
        return subprocess.check_output(
            ["git", "--no-pager", "show", f"HEAD:{relpath}"],
            cwd=str(repo),
        )
    except subprocess.CalledProcessError:
        return None


def commit_if_changed(repo: Path | str, files: Iterable[Path | str], message: str) -> bool:
    """Legacy helper: compares working tree to HEAD for listed files and commits if changed."""
    repo = Path(repo)
    # Stage then compare staged content
    return safe_commit(repo, files, message)


def _index_file_bytes(repo: Path, relpath: str) -> bytes | None:
    try:
        return subprocess.check_output(["git", "--no-pager", "show", f":{relpath}"], cwd=str(repo))
    except subprocess.CalledProcessError:
        return None


def safe_commit(repo: Path | str, files: Iterable[Path | str], message: str) -> bool:
    """Commit only if staged file content differs from HEAD for any given file.

    Steps:
    - git add <files>
    - Compare index blob (:path) to HEAD:path
    - If all equal → skip commit
    - Else commit
    """
    repo = Path(repo)
    # Stage files
    paths = [str(Path(f).relative_to(repo)) for f in files]
    subprocess.check_call(["git", "add", *paths], cwd=str(repo))

    changed = False
    for rel in paths:
        head = _head_file_bytes(repo, rel)
        index = _index_file_bytes(repo, rel)
        if head != index:
            changed = True
            break

    if not changed:
        logger.info("git.nochange", files=paths)
        return False

    subprocess.check_call(["git", "commit", "-m", message], cwd=str(repo))
    logger.info("git.committed", files=paths)
    return True
