from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Dict, Optional

import httpx
from bs4 import BeautifulSoup


@dataclass
class PersonRow:
    name: Optional[str]
    age: Optional[str]
    roll_number: Optional[str]
    tribe: Optional[str]
    household: Optional[str]
    other: Dict[str, str]


async def fetch_parse_people_table(url: str) -> List[PersonRow]:
    """Fetch an AccessGenealogy page and parse the first tabular people list.

    Heuristics: map common headers to canonical fields (name, age, roll_number, tribe, household).
    Returns a list of PersonRow entries; may be empty if no table detected.
    """
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

    table = soup.find("table")
    if not table:
        return []

    # Extract headers (normalize)
    headers = [h.get_text(strip=True) for h in table.find_all("th")]
    header_map = _build_header_map(headers)

    rows: List[PersonRow] = []
    for tr in table.find_all("tr")[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if not cells:
            continue
        data: Dict[str, str] = {}
        for idx, val in enumerate(cells):
            key = header_map.get(idx)
            if key:
                data[key] = val
        rows.append(
            PersonRow(
                name=data.get("name"),
                age=data.get("age"),
                roll_number=data.get("roll"),
                tribe=data.get("tribe"),
                household=data.get("household"),
                other={k: v for k, v in data.items() if k not in {"name", "age", "roll", "tribe", "household"}},
            )
        )

    return rows


def _build_header_map(headers: List[str]) -> Dict[int, str]:
    canonical = {}
    for i, h in enumerate(headers):
        hl = h.lower()
        if any(k in hl for k in ["name", "person", "applicant"]):
            canonical[i] = "name"
        elif "age" in hl or "yrs" in hl:
            canonical[i] = "age"
        elif "roll" in hl or "enroll" in hl or "card" in hl or "no." in hl:
            canonical[i] = "roll"
        elif "tribe" in hl or "nation" in hl:
            canonical[i] = "tribe"
        elif "household" in hl or "fam" in hl:
            canonical[i] = "household"
        else:
            # keep header text as fallback key
            canonical[i] = hl.replace(" ", "_")[:32]
    return canonical
