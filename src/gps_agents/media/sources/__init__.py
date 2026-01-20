"""Photo source adapters for downloading public domain images."""

from .base import PhotoSource, PhotoResult, DownloadedPhoto, CommonsBundle
from .usaf import USAFPhotoSource
from .commons import CommonsDuplicateChecker

__all__ = [
    "PhotoSource",
    "PhotoResult",
    "DownloadedPhoto",
    "CommonsBundle",
    "USAFPhotoSource",
    "CommonsDuplicateChecker",
]
