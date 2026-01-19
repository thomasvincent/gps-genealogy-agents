from __future__ import annotations

import hashlib
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def storage_path(root: Path | str, sha256_hex: str) -> Path:
    root = Path(root)
    return root / sha256_hex[:2] / sha256_hex[2:4] / sha256_hex


def save_media_bytes(data: bytes, root: Path | str) -> Path:
    """Save media by content hash. If exists, do not duplicate.

    Returns the path to the stored file.
    """
    h = sha256_bytes(data)
    path = storage_path(root, h)
    if path.exists():
        logger.info("media.exists", path=str(path))
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    from gps_agents.fs import atomic_write
    atomic_write(path, data)
    logger.info("media.saved", path=str(path))
    return path


def link_media_file(src: Path | str, root: Path | str) -> Path:
    src = Path(src)
    data = src.read_bytes()
    return save_media_bytes(data, root)
