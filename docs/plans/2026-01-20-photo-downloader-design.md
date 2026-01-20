# Photo Downloader for Wikimedia Commons

**Date:** 2026-01-20
**Status:** Approved

## Overview

Download public domain photos from government sources with metadata formatted for Wikimedia Commons upload. Outputs a bundle compatible with batch upload tools (Pattypan, VicuñaUploader).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   PhotoDownloader                        │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ USAFPhotos   │  │ NARAPhotos   │  │ LOCPhotos    │  │
│  │ (af.mil)     │  │ (catalog)    │  │ (loc.gov)    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│           │               │               │             │
│           └───────────────┼───────────────┘             │
│                           ▼                             │
│                  ┌────────────────┐                     │
│                  │ CommonsDupCheck│                     │
│                  │ (skip existing)│                     │
│                  └────────────────┘                     │
│                           │                             │
│                           ▼                             │
│                  ┌────────────────┐                     │
│                  │ MetadataMapper │                     │
│                  │ → {{Information}}                    │
│                  └────────────────┘                     │
│                           │                             │
│                           ▼                             │
│         research/<subject>/photos/                      │
│         ├── photo1.jpg                                  │
│         ├── photo2.jpg                                  │
│         └── upload-manifest.csv                         │
└─────────────────────────────────────────────────────────┘
```

## Photo Sources

### USAF Photos (af.mil)
- URL pattern: `https://www.af.mil/News/Photos/` and biography pages
- License: `{{PD-USGov-Military-Air Force}}`
- Metadata: Caption, date, photographer (sometimes)

### NARA Catalog (catalog.archives.gov)
- API: `https://catalog.archives.gov/api/v1/`
- License: `{{PD-USGov}}`
- Metadata: Title, description, date, record group, NAID

### Library of Congress (loc.gov)
- API: `https://www.loc.gov/photos/` with JSON endpoint
- License: Most public domain (verify per item)
- Metadata: Title, date, creator, rights statement

### DOE (energy.gov)
- Historical photo archives, press releases
- License: `{{PD-USGov-DOE}}`
- Metadata: Caption, date, context

## Commons Duplicate Check

Query Wikimedia Commons API before downloading:
- Search File namespace for subject name
- Check if source URL already exists in file descriptions
- Skip duplicates, report in bundle output

## Metadata Mapping

Maps source metadata to Commons `{{Information}}` template:

| Commons Field | Source |
|---------------|--------|
| `description` | Photo caption + subject context |
| `date` | From source metadata or "circa YYYY" |
| `source` | Original URL |
| `author` | Photographer if known, else agency name |
| `permission` | License template (e.g., `{{PD-USGov-Military-Air Force}}`) |
| `other versions` | Link to higher/lower res if available |

## Data Models

```python
@dataclass
class PhotoResult:
    """A photo found from a government source."""
    source_name: str           # "USAF", "NARA", "LOC", "DOE"
    source_url: str            # Original page URL
    image_url: str             # Direct image download URL
    title: str                 # Photo title/caption
    date: str | None           # Date taken or published
    author: str | None         # Photographer or agency
    license_template: str      # e.g., "{{PD-USGov-Military-Air Force}}"
    description: str | None    # Extended description

@dataclass
class DownloadedPhoto:
    """A downloaded photo with metadata."""
    local_path: Path           # Where saved locally
    filename: str              # Commons-safe filename
    photo: PhotoResult         # Original metadata
    sha256: str                # File hash for verification

@dataclass
class CommonsBundle:
    """Complete bundle ready for upload."""
    subject_id: str            # e.g., "archer-l-durham"
    photos_dir: Path           # research/<subject>/photos/
    manifest_path: Path        # upload-manifest.csv
    photos: list[DownloadedPhoto]
    skipped_duplicates: list[str]  # Already on Commons
```

## Interface

```python
class PhotoDownloader:
    async def search_all_sources(
        self,
        subject_name: str,
        birth_year: int | None = None,
        keywords: list[str] | None = None
    ) -> list[PhotoResult]

    async def download_bundle(
        self,
        subject_id: str,
        photos: list[PhotoResult],
        output_dir: Path
    ) -> CommonsBundle
```

## Output Format

### Directory Structure
```
research/archer-l-durham/
├── photos/
│   ├── Archer_L_Durham_USAF_official.jpg
│   ├── Archer_L_Durham_DOE_1995.jpg
│   └── upload-manifest.csv
```

### upload-manifest.csv
```csv
filename,description,date,source,author,license,categories
Archer_L_Durham_USAF.jpg,"Major General Archer L. Durham...",1987,https://...,U.S. Air Force,{{PD-USGov-Military-Air Force}},"1932 births; United States Air Force generals"
```

Compatible with Pattypan and VicuñaUploader batch upload tools.

## Error Handling

| Scenario | Handling |
|----------|----------|
| Source unavailable | Log warning, continue with other sources |
| Rate limited (429) | Use existing circuit breaker |
| Image download fails | Retry 3x with backoff, skip if failing |
| Invalid image | Verify with PIL, exclude from manifest |
| Commons API unavailable | Proceed without duplicate check, warn |
| No photos found | Return empty bundle, log info |

## File Structure

```
src/gps_agents/media/
├── store.py                    # Existing
├── photo_downloader.py         # Main downloader class
└── sources/
    ├── __init__.py
    ├── base.py                 # PhotoSource protocol
    ├── usaf.py
    ├── nara.py
    ├── loc.py
    └── commons.py              # Duplicate checker

tests/
└── test_photo_downloader.py
```

## Testing

- Mock HTTP responses for each source
- Test metadata extraction with real HTML samples
- Test CSV generation matches Pattypan format
- Integration test with one real download
