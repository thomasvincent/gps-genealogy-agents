"""GEDCOM file parser for local genealogy files."""

from datetime import UTC, datetime
from pathlib import Path

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource


class GedcomSource(BaseSource):
    """GEDCOM file parser for local genealogy data.

    Parses standard GEDCOM files (.ged) which are the universal
    format for exchanging genealogical data.
    """

    name = "GEDCOM"

    def __init__(self, file_path: str | Path | None = None) -> None:
        """Initialize GEDCOM source.

        Args:
            file_path: Path to GEDCOM file
        """
        super().__init__()
        self.file_path = Path(file_path) if file_path else None
        self._individuals: dict[str, dict] = {}
        self._families: dict[str, dict] = {}
        self._loaded = False

    def requires_auth(self) -> bool:
        return False

    def is_configured(self) -> bool:
        return self.file_path is not None and self.file_path.exists()

    def load_file(self, file_path: str | Path | None = None) -> int:
        """Load and parse a GEDCOM file.

        Args:
            file_path: Path to file (uses instance path if not provided)

        Returns:
            Number of individuals loaded
        """
        path = Path(file_path) if file_path else self.file_path
        if not path or not path.exists():
            raise FileNotFoundError(f"GEDCOM file not found: {path}")

        self.file_path = path
        self._individuals = {}
        self._families = {}

        current_record = None
        current_id = None

        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = line.split(" ", 2)
                level = int(parts[0])
                tag = parts[1] if len(parts) > 1 else ""
                value = parts[2] if len(parts) > 2 else ""

                if level == 0:
                    # Save previous record
                    if current_record and current_id:
                        if current_record.get("_type") == "INDI":
                            self._individuals[current_id] = current_record
                        elif current_record.get("_type") == "FAM":
                            self._families[current_id] = current_record

                    # Start new record
                    if tag.startswith("@") and value in ("INDI", "FAM"):
                        current_id = tag
                        current_record = {"_type": value, "_id": tag}
                    else:
                        current_record = None
                        current_id = None

                elif current_record is not None:
                    # Add to current record
                    if level == 1:
                        if tag == "NAME":
                            current_record["name"] = value
                        elif tag == "SEX":
                            current_record["sex"] = value
                        elif tag == "BIRT":
                            current_record["_current_event"] = "birth"
                        elif tag == "DEAT":
                            current_record["_current_event"] = "death"
                        elif tag == "MARR":
                            current_record["_current_event"] = "marriage"
                        elif tag == "HUSB":
                            current_record["husband"] = value
                        elif tag == "WIFE":
                            current_record["wife"] = value
                        elif tag == "CHIL":
                            current_record.setdefault("children", []).append(value)
                        elif tag == "FAMC":
                            current_record["family_child"] = value
                        elif tag == "FAMS":
                            current_record.setdefault("family_spouse", []).append(value)
                    elif level == 2:
                        event = current_record.get("_current_event")
                        if event:
                            if tag == "DATE":
                                current_record[f"{event}_date"] = value
                            elif tag == "PLAC":
                                current_record[f"{event}_place"] = value

        # Save last record
        if current_record and current_id:
            if current_record.get("_type") == "INDI":
                self._individuals[current_id] = current_record
            elif current_record.get("_type") == "FAM":
                self._families[current_id] = current_record

        self._loaded = True
        return len(self._individuals)

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search loaded GEDCOM data.

        Args:
            query: Search parameters

        Returns:
            List of matching records
        """
        if not self._loaded and self.is_configured():
            self.load_file()

        records = []

        for indi_id, indi in self._individuals.items():
            if self._matches_query(indi, query):
                record = self._individual_to_record(indi_id, indi)
                if record:
                    records.append(record)

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific individual by GEDCOM ID.

        Args:
            record_id: GEDCOM individual ID (e.g., @I123@)

        Returns:
            The record or None
        """
        if not self._loaded and self.is_configured():
            self.load_file()

        indi = self._individuals.get(record_id)
        if not indi:
            return None

        return self._individual_to_record(record_id, indi)

    def _matches_query(self, indi: dict, query: SearchQuery) -> bool:
        """Check if individual matches search query.

        Args:
            indi: Individual data
            query: Search parameters

        Returns:
            True if matches
        """
        name = indi.get("name", "").lower()

        # GEDCOM names use /Surname/ format
        if query.surname and query.surname.lower() not in name:
            return False

        if query.given_name and query.given_name.lower() not in name:
            return False

        if query.birth_year:
            birth_date = indi.get("birth_date", "")
            if birth_date:
                try:
                    year = int("".join(c for c in birth_date if c.isdigit())[:4])
                    if abs(year - query.birth_year) > query.birth_year_range:
                        return False
                except ValueError:
                    pass

        if query.birth_place:
            birth_place = indi.get("birth_place", "").lower()
            if query.birth_place.lower() not in birth_place:
                return False

        return True

    def _individual_to_record(self, indi_id: str, indi: dict) -> RawRecord | None:
        """Convert GEDCOM individual to RawRecord.

        Args:
            indi_id: GEDCOM ID
            indi: Individual data

        Returns:
            RawRecord or None
        """
        name = indi.get("name", "")

        # Parse name (format: Given /Surname/)
        given_name = ""
        surname = ""
        if "/" in name:
            parts = name.split("/")
            given_name = parts[0].strip()
            surname = parts[1].strip() if len(parts) > 1 else ""
        else:
            given_name = name

        extracted = {
            "gedcom_id": indi_id,
            "full_name": name.replace("/", "").strip(),
            "given_name": given_name,
            "surname": surname,
            "sex": indi.get("sex"),
            "birth_date": indi.get("birth_date"),
            "birth_place": indi.get("birth_place"),
            "death_date": indi.get("death_date"),
            "death_place": indi.get("death_place"),
        }

        return RawRecord(
            source=self.name,
            record_id=indi_id,
            record_type="individual",
            url=str(self.file_path) if self.file_path else None,
            raw_data=indi,
            extracted_fields={k: v for k, v in extracted.items() if v},
            accessed_at=datetime.now(UTC),
        )

    def get_family(self, family_id: str) -> dict | None:
        """Get family record by ID.

        Args:
            family_id: GEDCOM family ID

        Returns:
            Family data or None
        """
        return self._families.get(family_id)

    def get_parents(self, individual_id: str) -> tuple[dict | None, dict | None]:
        """Get parents of an individual.

        Args:
            individual_id: GEDCOM individual ID

        Returns:
            Tuple of (father, mother) data
        """
        indi = self._individuals.get(individual_id)
        if not indi:
            return None, None

        family_id = indi.get("family_child")
        if not family_id:
            return None, None

        family = self._families.get(family_id)
        if not family:
            return None, None

        father = self._individuals.get(family.get("husband"))
        mother = self._individuals.get(family.get("wife"))

        return father, mother
