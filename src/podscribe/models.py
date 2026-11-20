"""Shared types for the podscribe pipeline.

Every lane depends on these types; changes go through the orchestrator.
Terms follow the glossary: episode link, show, feed, feed match, transcript,
cleaned transcript, episode note.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


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


@dataclass(frozen=True, slots=True)
class Segment:
    """One timestamped piece of a transcript.

    Attributes:
        start_seconds: Offset from the start of the episode.
        text: The speech in this piece.
    """

    start_seconds: float
    text: str

    @property
    def timestamp(self) -> str:
        """Return the start offset as ``hh:mm:ss``."""
        hours, rest = divmod(int(self.start_seconds), 3600)
        minutes, seconds = divmod(rest, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@dataclass(frozen=True, slots=True)
class Transcript:
    """The time-stamped speech of one episode, before any cleanup pass.

    Attributes:
        segments: Timestamped pieces in playback order.
        language: Language code the engine reported.
        model: Concrete speech model id, as written to the note.
        plan: Which speech plan produced most segments: plan1, plan2 or mixed.
        transcribed_at: When transcription finished.
        timed: Whether the segments carry analyzer-reported timestamps.
    """

    segments: tuple[Segment, ...]
    language: str
    model: str
    plan: str = "plan1"
    transcribed_at: datetime | None = None
    timed: bool = True


@dataclass(frozen=True, slots=True)
class EpisodeNote:
    """Everything an episode note needs; note.py renders it.

    Attributes:
        ref: The episode link and its show metadata.
        feed_url: Public feed the audio and show notes came from.
        transcript: Time-stamped speech, cleaned when cleanup succeeded.
        duration_seconds: Episode duration when the feed states one.
        summary: English summary, None when the summary pass failed.
        key_points: Bullet points, empty when the summary pass failed.
        tags: Lowercase tags for the note frontmatter.
        cleanup: done, partial (drift guard) or skipped (LLM failure).
    """

    ref: EpisodeRef
    feed_url: str
    transcript: Transcript
    duration_seconds: int | None = None
    summary: str | None = None
    key_points: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    cleanup: str = "done"
