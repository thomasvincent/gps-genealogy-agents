from __future__ import annotations

import re
from typing import Dict, Optional


def parse_index_row(row: str) -> Dict[str, Optional[str]]:
    """Parse a FreeBMD index row string into fields.

    Row is a ' | '-joined string of TDs produced by the source. We try to pull:
    - event (birth/death/marriage)
    - year (4-digit)
    - quarter (Mar/Jun/Sep/Dec or Q1..Q4)
    - district
    - volume
    - page
    - name (if present in first cell)
    """
    parts = [p.strip() for p in row.split("|") if p.strip()]
    data: Dict[str, Optional[str]] = {
        "event": None,
        "year": None,
        "quarter": None,
        "district": None,
        "volume": None,
        "page": None,
        "name": None,
    }

    # Name heuristic: first field if it looks like 'Surname, Given' or has a space
    if parts:
        if "," in parts[0] or " " in parts[0]:
            data["name"] = parts[0]

    # Event
    for p in parts:
        low = p.lower()
        if "birth" in low:
            data["event"] = "birth"
            break
        if "death" in low:
            data["event"] = "death"
            break
        if "marriage" in low:
            data["event"] = "marriage"
            break

    # Year and quarter
    m = re.search(r"(18|19|20)\d{2}", row)
    if m:
        data["year"] = m.group(0)
    qm = re.search(r"\b(Q[1-4]|Mar|Jun|Sep|Dec)\b", row, re.IGNORECASE)
    if qm:
        data["quarter"] = qm.group(0)

    # Volume and Page
    vm = re.search(r"\bVol(?:ume)?\s*([A-Z0-9]+)|\b([A-Z0-9]{1,4})\b(?=\s*Vol)", row, re.IGNORECASE)
    pm = re.search(r"\bPage\s*([0-9A-Z]+)\b", row, re.IGNORECASE)
    if vm:
        data["volume"] = vm.group(1) or vm.group(2)
    if pm:
        data["page"] = pm.group(1)

    # District (best-effort: look for token after 'District' or bracketed)
    dm = re.search(r"District\s*([A-Za-z\-\s]+?)(?:\bVol|\bPage|$)", row)
    if dm:
        data["district"] = dm.group(1).strip()

    return data
