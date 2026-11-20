"""Shared types for the podscribe pipeline.

Every lane depends on these types; changes go through the orchestrator.
Terms follow the glossary: episode link, show, feed, feed match, transcript,
cleaned transcript, episode note.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class EpisodeRef:
    """One episode link, identified from the public Spotify episode page.

    Attributes:
        spotify_url: The episode link the user sent.
        show: Name of the show the episode belongs to.
        episode_title: Title of the episode as Spotify shows it.
        published_at: Publish date when the page carries one.
    """

    spotify_url: str
    show: str
    episode_title: str
    published_at: date | None = None


@dataclass(frozen=True, slots=True)
class FeedItem:
    """One item in a show's public feed - the only source of audio.

    Attributes:
        title: Item title from the feed.
        published_at: Publish date of the item.
        audio_url: Enclosure URL to download.
        duration_seconds: Duration when the feed states one.
        show_notes: Item description, used as the name list for cleanup.
        guid: Feed guid, when present.
    """

    title: str
    published_at: date
    audio_url: str
    duration_seconds: int | None = None
    show_notes: str = ""
    guid: str | None = None
