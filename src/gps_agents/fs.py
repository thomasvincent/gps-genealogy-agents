from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path | str, data: bytes) -> Path:
    """Atomically write bytes to a path.

    Writes to a temporary file in the same directory, fsyncs, then renames.
    """
    target = Path(path)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
        return target
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
