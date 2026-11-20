"""Download an episode's audio enclosure into a working directory."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from podscribe.http import HttpClientLike
from podscribe.models import FeedItem

DEFAULT_AUDIO_NAME = "episode.mp3"
URL_TAG_LENGTH = 10


def _url_tag(url: str) -> str:
    """Return a short stable tag for an enclosure URL."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:URL_TAG_LENGTH]


def audio_filename(item: FeedItem) -> str:
    """Return a cache file name unique to the enclosure URL.

    The URL path's stem and suffix are kept for readability; a short hash of
    the whole URL keeps two enclosures that share a basename apart.
    """
    path = PurePosixPath(urlparse(item.audio_url).path)
    default = PurePosixPath(DEFAULT_AUDIO_NAME)
    stem = path.stem or default.stem
    suffix = path.suffix or default.suffix
    return f"{stem}-{_url_tag(item.audio_url)}{suffix}"


def download_audio(item: FeedItem, directory: Path, client: HttpClientLike, *, overwrite: bool = False) -> Path:
    """Download ``item``'s audio enclosure into ``directory``.

    Args:
        item: Feed item holding the enclosure URL.
        directory: Directory to write into; created when missing.
        client: HTTP client used for the download.
        overwrite: Re-download when the destination already exists.

    Returns:
        Path of the downloaded audio file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / audio_filename(item)
    if destination.exists() and not overwrite:
        return destination
    return client.download(item.audio_url, destination)
