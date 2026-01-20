"""USAF photo source adapter for official military portraits and photos."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from .base import DownloadedPhoto, PhotoResult, compute_sha256

logger = logging.getLogger(__name__)


class USAFPhotoSource:
    """Adapter for U.S. Air Force official photos from af.mil."""

    name = "USAF"
    base_url = "https://www.af.mil"
    license_template = "{{PD-USGov-Military-Air Force}}"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research; contact@example.com)"
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search(
        self,
        subject_name: str,
        birth_year: int | None = None,
        keywords: list[str] | None = None,
    ) -> list[PhotoResult]:
        """Search for USAF photos of the subject.

        Searches:
        1. Biography pages (official portraits)
        2. News/Photos section
        """
        results: list[PhotoResult] = []

        # Search biography pages first (most reliable for portraits)
        bio_results = await self._search_biographies(subject_name)
        results.extend(bio_results)

        # Search photo galleries
        gallery_results = await self._search_photo_galleries(subject_name, keywords)
        results.extend(gallery_results)

        return results

    async def _search_biographies(self, subject_name: str) -> list[PhotoResult]:
        """Search USAF biographies for official portraits."""
        results: list[PhotoResult] = []
        client = await self._get_client()

        # Build search URL for biographies
        # Format: /About-Us/Biographies/?q=name
        search_url = f"{self.base_url}/About-Us/Biographies/"
        params = {"q": subject_name}

        try:
            resp = await client.get(search_url, params=params)
            resp.raise_for_status()
            html = resp.text

            soup = BeautifulSoup(html, "html.parser")

            # Find biography links
            for link in soup.select("a[href*='/Biographies/Display/']"):
                bio_url = link.get("href", "")
                if not bio_url:
                    continue

                # Make absolute URL
                if bio_url.startswith("/"):
                    bio_url = f"{self.base_url}{bio_url}"

                # Check if name matches
                link_text = link.get_text(strip=True).lower()
                name_parts = subject_name.lower().split()
                if not any(part in link_text for part in name_parts):
                    continue

                # Fetch the biography page to get the photo
                photo_result = await self._extract_bio_photo(bio_url, subject_name)
                if photo_result:
                    results.append(photo_result)

        except httpx.HTTPError as e:
            logger.warning(f"USAF biography search failed: {e}")

        return results

    async def _extract_bio_photo(
        self, bio_url: str, subject_name: str
    ) -> PhotoResult | None:
        """Extract photo from a biography page."""
        client = await self._get_client()

        try:
            resp = await client.get(bio_url)
            resp.raise_for_status()
            html = resp.text

            soup = BeautifulSoup(html, "html.parser")

            # Find the main biography photo
            # Common patterns: .bio-photo img, .portrait img, article img
            photo_selectors = [
                ".bio-photo img",
                ".portrait img",
                ".biography-image img",
                "article .photo img",
                ".af-article-figure img",
                "figure img",
            ]

            image_url = None
            for selector in photo_selectors:
                img = soup.select_one(selector)
                if img:
                    image_url = img.get("src") or img.get("data-src")
                    if image_url:
                        break

            # Fallback: find any large image in the article
            if not image_url:
                for img in soup.select("img"):
                    src = img.get("src", "")
                    # Skip small icons and thumbnails
                    if any(
                        x in src.lower()
                        for x in ["icon", "logo", "thumb", "avatar", "spacer"]
                    ):
                        continue
                    if src and (".jpg" in src.lower() or ".jpeg" in src.lower()):
                        image_url = src
                        break

            if not image_url:
                logger.debug(f"No photo found on biography page: {bio_url}")
                return None

            # Make absolute URL
            if image_url.startswith("/"):
                image_url = f"{self.base_url}{image_url}"
            elif not image_url.startswith("http"):
                image_url = f"{self.base_url}/{image_url}"

            # Extract title and date from page
            title_tag = soup.select_one("h1, .title, .bio-name")
            title = title_tag.get_text(strip=True) if title_tag else subject_name

            # Try to find date
            date = None
            date_tag = soup.select_one(".date, .published, time")
            if date_tag:
                date = date_tag.get_text(strip=True)

            # Build description
            description = f"Official U.S. Air Force portrait of {title}"

            return PhotoResult(
                source_name=self.name,
                source_url=bio_url,
                image_url=image_url,
                title=f"{title} - USAF Official Portrait",
                date=date,
                author="U.S. Air Force",
                license_template=self.license_template,
                description=description,
                categories=[
                    "United States Air Force generals",
                    "Military personnel portraits",
                ],
            )

        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch biography page {bio_url}: {e}")
            return None

    async def _search_photo_galleries(
        self, subject_name: str, keywords: list[str] | None
    ) -> list[PhotoResult]:
        """Search USAF photo galleries."""
        results: list[PhotoResult] = []
        client = await self._get_client()

        # Build search terms
        search_terms = subject_name
        if keywords:
            search_terms = f"{subject_name} {' '.join(keywords)}"

        # Search photos section
        search_url = f"{self.base_url}/News/Photos/"
        params = {"q": search_terms}

        try:
            resp = await client.get(search_url, params=params)
            resp.raise_for_status()
            html = resp.text

            soup = BeautifulSoup(html, "html.parser")

            # Find photo items in gallery
            for item in soup.select(".photo-item, .gallery-item, .news-item"):
                link = item.select_one("a")
                img = item.select_one("img")

                if not link or not img:
                    continue

                page_url = link.get("href", "")
                if page_url.startswith("/"):
                    page_url = f"{self.base_url}{page_url}"

                # Get image URL (may need to fetch full-res from detail page)
                image_url = img.get("src") or img.get("data-src", "")
                if image_url.startswith("/"):
                    image_url = f"{self.base_url}{image_url}"

                # Get title
                title_elem = item.select_one(".title, .caption, h3, h4")
                title = (
                    title_elem.get_text(strip=True) if title_elem else "USAF Photo"
                )

                # Verify subject name appears in title/caption
                if not any(
                    part.lower() in title.lower()
                    for part in subject_name.split()
                ):
                    continue

                results.append(
                    PhotoResult(
                        source_name=self.name,
                        source_url=page_url,
                        image_url=image_url,
                        title=title,
                        date=None,
                        author="U.S. Air Force",
                        license_template=self.license_template,
                        description=title,
                        categories=["United States Air Force"],
                    )
                )

        except httpx.HTTPError as e:
            logger.warning(f"USAF photo gallery search failed: {e}")

        return results

    async def download(
        self,
        photo: PhotoResult,
        dest_dir: Path,
        filename: str | None = None,
    ) -> DownloadedPhoto | None:
        """Download a photo to the destination directory."""
        client = await self._get_client()

        if filename is None:
            # Extract filename from URL or generate one
            url_path = photo.image_url.split("/")[-1].split("?")[0]
            if url_path and "." in url_path:
                filename = url_path
            else:
                filename = f"{photo.source_name}_{hash(photo.image_url)}.jpg"

        # Clean filename
        filename = re.sub(r"[^\w\-_.]", "_", filename)

        dest_path = dest_dir / filename
        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            resp = await client.get(photo.image_url)
            resp.raise_for_status()

            # Verify it's an image
            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type.lower():
                logger.warning(
                    f"Not an image ({content_type}): {photo.image_url}"
                )
                return None

            data = resp.content
            sha256 = compute_sha256(data)

            # Write file
            dest_path.write_bytes(data)

            logger.info(f"Downloaded {photo.image_url} -> {dest_path}")

            return DownloadedPhoto(
                local_path=dest_path,
                filename=filename,
                photo=photo,
                sha256=sha256,
            )

        except httpx.HTTPError as e:
            logger.error(f"Failed to download {photo.image_url}: {e}")
            return None

    async def __aenter__(self) -> "USAFPhotoSource":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
