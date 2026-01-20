from __future__ import annotations

from typing import Dict, Optional

import httpx
from bs4 import BeautifulSoup


async def fetch_parse_memorial(url: str) -> Dict[str, Optional[str]]:
    """Fetch a Find A Grave memorial and parse a few structured fields.

    Best-effort: name, birth_date, death_date, cemetery_name, cemetery_location.
    """
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

    data: Dict[str, Optional[str]] = {
        "name": None,
        "birth_date": None,
        "death_date": None,
        "cemetery_name": None,
        "cemetery_location": None,
    }

    # Family members (best-effort) – look for headings like 'Family Members', 'Parents', 'Spouse', 'Children'
    family: Dict[str, list[str]] = {"parents": [], "spouses": [], "children": []}
    # Find any section headings
    headings = soup.find_all(["h2", "h3", "h4"]) or []
    for hd in headings:
        text = hd.get_text(strip=True).lower()
        if "family" in text or "parents" in text or "spouse" in text or "children" in text:
            # Collect links in the following sibling container
            sib = hd.find_next_sibling()
            if sib:
                for a in sib.find_all("a"):
                    label = a.get_text(strip=True)
                    if not label:
                        continue
                    # Heuristic bucket by surrounding text
                    ctx = sib.get_text(" ", strip=True).lower()
                    if "parent" in text or "parent" in ctx:
                        family["parents"].append(label)
                    elif "spouse" in text or "spouse" in ctx:
                        family["spouses"].append(label)
                    elif "children" in text or "child" in ctx:
                        family["children"].append(label)
    # Attach when any found
    if any(family.values()):
        data["family_members"] = family  # type: ignore[assignment]

    # Name: try title or h1
    title = soup.find("title")
    if title:
        data["name"] = title.get_text(strip=True).replace("- Find a Grave Memorial", "").strip()
    h1 = soup.find("h1")
    if h1 and not data["name"]:
        data["name"] = h1.get_text(strip=True)

    # Birth/Death dates - look for labels
    for label in soup.find_all(text=True):
        t = label.strip()
        if not t:
            continue
        low = t.lower()
        if low.startswith("born") and not data["birth_date"]:
            data["birth_date"] = t.split(" ", 1)[-1].strip()
        if low.startswith("died") and not data["death_date"]:
            data["death_date"] = t.split(" ", 1)[-1].strip()

    # Cemetery name/location: look for links containing '/cemetery/'
    cem_link = soup.find("a", href=lambda h: h and "/cemetery/" in h)
    if cem_link:
        data["cemetery_name"] = cem_link.get_text(strip=True)
        # Parent text might include location
        parent_text = cem_link.find_parent().get_text(" ", strip=True) if cem_link.find_parent() else ""
        if parent_text:
            data["cemetery_location"] = parent_text.replace(data["cemetery_name"] or "", "").strip(" ,")

    return data
