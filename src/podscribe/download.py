"""Download an episode's audio enclosure into a working directory."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from podscribe.http import HttpClientLike
from podscribe.models import FeedItem

DEFAULT_AUDIO_NAME = "episode.mp3"


def audio_filename(item: FeedItem) -> str:
    """Return the enclosure's file name, falling back to a default."""
    return PurePosixPath(urlparse(item.audio_url).path).name or DEFAULT_AUDIO_NAME


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
