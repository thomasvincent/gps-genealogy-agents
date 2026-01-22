"""Base protocol and data models for photo sources."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime


from pathlib import Path
from typing import Protocol, runtime_checkable


def _utc_now() -> datetime:
    """Return current UTC time (for use as default_factory)."""
    return datetime.now(UTC)


@dataclass
class PhotoResult:
    """A photo found from a government source."""

    source_name: str  # "USAF", "NARA", "LOC", "DOE"
    source_url: str  # Original page URL
    image_url: str  # Direct image download URL
    title: str  # Photo title/caption
    date: str | None = None  # Date taken or published
    author: str | None = None  # Photographer or agency
    license_template: str = "{{PD-USGov}}"  # Wikimedia Commons license template
    description: str | None = None  # Extended description
    categories: list[str] = field(default_factory=list)  # Suggested Commons categories

    def to_commons_filename(self, subject_name: str) -> str:
        """Generate a Commons-safe filename."""
        # Remove special characters, replace spaces with underscores
        safe_name = re.sub(r"[^\w\s-]", "", subject_name)
        safe_name = re.sub(r"\s+", "_", safe_name.strip())

        # Add source suffix
        suffix = self.source_name.replace(" ", "_")

        # Add date if available
        if self.date:
            year_match = re.search(r"\d{4}", self.date)
            if year_match:
                suffix = f"{suffix}_{year_match.group()}"

        return f"{safe_name}_{suffix}.jpg"


@dataclass
class DownloadedPhoto:
    """A downloaded photo with metadata."""

    local_path: Path  # Where saved locally
    filename: str  # Commons-safe filename
    photo: PhotoResult  # Original metadata
    sha256: str  # File hash for verification
    download_time: datetime = field(default_factory=_utc_now)

    def to_manifest_row(self) -> dict[str, str]:
        """Convert to a row for upload-manifest.csv."""
        return {
            "filename": self.filename,
            "description": self.photo.description or self.photo.title,
            "date": self.photo.date or "",
            "source": self.photo.source_url,
            "author": self.photo.author or self.photo.source_name,
            "license": self.photo.license_template,
            "categories": "; ".join(self.photo.categories),
        }


@dataclass
class CommonsBundle:
    """Complete bundle ready for upload to Wikimedia Commons."""

    subject_id: str  # e.g., "archer-l-durham"
    subject_name: str  # e.g., "Archer L. Durham"
    photos_dir: Path  # research/<subject>/photos/
    manifest_path: Path  # upload-manifest.csv
    photos: list[DownloadedPhoto] = field(default_factory=list)
    skipped_duplicates: list[str] = field(default_factory=list)  # Already on Commons
    errors: list[str] = field(default_factory=list)  # Download failures

    def write_manifest(self) -> Path:
        """Write upload-manifest.csv for Pattypan/VicuñaUploader."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "filename",
            "description",
            "date",
            "source",
            "author",
            "license",
            "categories",
        ]

        with open(self.manifest_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for photo in self.photos:
                writer.writerow(photo.to_manifest_row())

        return self.manifest_path


@runtime_checkable
class PhotoSource(Protocol):
    """Protocol for photo source adapters."""

    name: str

    async def search(
        self,
        subject_name: str,
        birth_year: int | None = None,
        keywords: list[str] | None = None,
    ) -> list[PhotoResult]:
        """Search for photos of the subject.

        Args:
            subject_name: Full name of the person
            birth_year: Optional birth year to narrow results
            keywords: Optional keywords (e.g., ["USAF", "military"])

        Returns:
            List of photo results found
        """
        ...

    async def download(
        self,
        photo: PhotoResult,
        dest_dir: Path,
        filename: str | None = None,
    ) -> DownloadedPhoto | None:
        """Download a photo to the destination directory.

        Args:
            photo: Photo result to download
            dest_dir: Directory to save the photo
            filename: Optional filename (otherwise generated)

        Returns:
            DownloadedPhoto if successful, None if failed
        """
        ...


def compute_sha256(data: bytes) -> str:
    """Compute SHA256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()
