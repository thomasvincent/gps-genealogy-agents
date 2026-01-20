"""Photo downloader for Wikimedia Commons upload preparation.

Downloads public domain photos from government sources with metadata
formatted for batch upload to Wikimedia Commons.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .sources.base import CommonsBundle, DownloadedPhoto, PhotoResult
from .sources.commons import CommonsDuplicateChecker
from .sources.usaf import USAFPhotoSource

logger = logging.getLogger(__name__)


class PhotoDownloader:
    """Download public domain photos for Wikimedia Commons upload.

    Searches government sources (USAF, NARA, LOC, DOE), checks for
    existing Commons files, and outputs a bundle ready for batch upload.
    """

    def __init__(self) -> None:
        self._usaf = USAFPhotoSource()
        self._commons = CommonsDuplicateChecker()
        # TODO: Add NARA, LOC, DOE sources

    async def close(self) -> None:
        """Close all HTTP connections."""
        await self._usaf.close()
        await self._commons.close()

    async def search_all_sources(
        self,
        subject_name: str,
        birth_year: int | None = None,
        keywords: list[str] | None = None,
    ) -> list[PhotoResult]:
        """Search all photo sources for the subject.

        Args:
            subject_name: Full name of the person
            birth_year: Optional birth year to narrow results
            keywords: Optional keywords (e.g., ["military", "general"])

        Returns:
            Combined list of photo results from all sources
        """
        results: list[PhotoResult] = []

        # Search USAF
        logger.info(f"Searching USAF photos for: {subject_name}")
        usaf_results = await self._usaf.search(subject_name, birth_year, keywords)
        results.extend(usaf_results)
        logger.info(f"Found {len(usaf_results)} USAF photos")

        # TODO: Search NARA
        # TODO: Search LOC
        # TODO: Search DOE

        return results

    async def check_commons_duplicates(
        self,
        subject_name: str,
        photos: list[PhotoResult],
    ) -> tuple[list[PhotoResult], list[str]]:
        """Filter out photos that already exist on Commons.

        Args:
            subject_name: Name of the subject
            photos: List of photo results to check

        Returns:
            Tuple of (photos_to_download, skipped_urls)
        """
        logger.info(f"Checking Commons for existing files: {subject_name}")

        # Get source URLs from photos
        source_urls = [p.source_url for p in photos]

        # Check for duplicates
        existing_files, urls_on_commons = await self._commons.check_duplicates(
            subject_name, source_urls
        )

        if existing_files:
            logger.info(
                f"Found {len(existing_files)} existing files on Commons: "
                f"{[f.title for f in existing_files]}"
            )

        # Filter out photos whose source URL is already on Commons
        filtered = []
        skipped = []
        for photo in photos:
            if photo.source_url in urls_on_commons:
                logger.info(f"Skipping (already on Commons): {photo.source_url}")
                skipped.append(photo.source_url)
            else:
                filtered.append(photo)

        return filtered, skipped

    async def download_photos(
        self,
        photos: list[PhotoResult],
        dest_dir: Path,
        subject_name: str,
    ) -> tuple[list[DownloadedPhoto], list[str]]:
        """Download photos to the destination directory.

        Args:
            photos: List of photos to download
            dest_dir: Directory to save photos
            subject_name: Subject name for filename generation

        Returns:
            Tuple of (downloaded_photos, error_messages)
        """
        downloaded: list[DownloadedPhoto] = []
        errors: list[str] = []

        dest_dir.mkdir(parents=True, exist_ok=True)

        for photo in photos:
            # Generate Commons-safe filename
            filename = photo.to_commons_filename(subject_name)

            # Route to appropriate source downloader
            result = None
            if photo.source_name == "USAF":
                result = await self._usaf.download(photo, dest_dir, filename)
            # TODO: Add other sources

            if result:
                downloaded.append(result)
                logger.info(f"Downloaded: {result.filename}")
            else:
                error_msg = f"Failed to download: {photo.image_url}"
                errors.append(error_msg)
                logger.error(error_msg)

        return downloaded, errors

    async def download_bundle(
        self,
        subject_id: str,
        subject_name: str,
        output_dir: Path,
        birth_year: int | None = None,
        keywords: list[str] | None = None,
        skip_commons_check: bool = False,
    ) -> CommonsBundle:
        """Search, filter, and download photos as a Commons-ready bundle.

        Args:
            subject_id: Identifier for the subject (e.g., "archer-l-durham")
            subject_name: Full name of the person
            output_dir: Base output directory (e.g., research/)
            birth_year: Optional birth year
            keywords: Optional search keywords
            skip_commons_check: If True, skip duplicate checking

        Returns:
            CommonsBundle with downloaded photos and manifest
        """
        photos_dir = output_dir / subject_id / "photos"
        manifest_path = photos_dir / "upload-manifest.csv"

        bundle = CommonsBundle(
            subject_id=subject_id,
            subject_name=subject_name,
            photos_dir=photos_dir,
            manifest_path=manifest_path,
        )

        # Search all sources
        all_photos = await self.search_all_sources(
            subject_name, birth_year, keywords
        )

        if not all_photos:
            logger.warning(f"No photos found for: {subject_name}")
            return bundle

        # Filter duplicates
        photos_to_download = all_photos
        if not skip_commons_check:
            photos_to_download, skipped = await self.check_commons_duplicates(
                subject_name, all_photos
            )
            bundle.skipped_duplicates = skipped

        if not photos_to_download:
            logger.info("All photos already exist on Commons")
            return bundle

        # Download photos
        downloaded, errors = await self.download_photos(
            photos_to_download, photos_dir, subject_name
        )

        bundle.photos = downloaded
        bundle.errors = errors

        # Write manifest
        if downloaded:
            bundle.write_manifest()
            logger.info(f"Wrote manifest: {manifest_path}")

        return bundle

    async def __aenter__(self) -> "PhotoDownloader":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()


async def download_photos_for_subject(
    subject_id: str,
    subject_name: str,
    output_dir: Path | str,
    birth_year: int | None = None,
    keywords: list[str] | None = None,
) -> CommonsBundle:
    """Convenience function to download photos for a subject.

    Args:
        subject_id: Identifier for the subject
        subject_name: Full name of the person
        output_dir: Base output directory
        birth_year: Optional birth year
        keywords: Optional search keywords

    Returns:
        CommonsBundle with results
    """
    output_dir = Path(output_dir)

    async with PhotoDownloader() as downloader:
        return await downloader.download_bundle(
            subject_id=subject_id,
            subject_name=subject_name,
            output_dir=output_dir,
            birth_year=birth_year,
            keywords=keywords,
        )
