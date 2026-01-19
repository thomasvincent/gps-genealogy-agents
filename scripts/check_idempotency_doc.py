#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

from gps_agents.idempotency.config import CONFIG


DOC = Path("docs/Idempotency.md").read_text(encoding="utf-8")

# Map of label -> value string expected to be present in docs
expected = {
    "merge_threshold": f"{CONFIG.merge_threshold}",
    "review_low": f"{CONFIG.review_low}",
    "review_high": f"{CONFIG.review_high}",
    "min_parent_age": f"{CONFIG.min_parent_age}",
    "max_parent_age": f"{CONFIG.max_parent_age}",
    "max_lifespan": f"{CONFIG.max_lifespan}",
}

missing = []
for k, v in expected.items():
    if v not in DOC:
        missing.append((k, v))

if missing:
    print("Idempotency docs missing default values for:")
    for k, v in missing:
        print(f" - {k}: {v}")
    raise SystemExit(1)
else:
    print("Idempotency docs are consistent with config.")
