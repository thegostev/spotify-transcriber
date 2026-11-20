"""Render episode notes and choose their Obsidian-safe file names."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from itertools import count
from pathlib import Path

from podscribe.models import EpisodeNote, EpisodeRef

UNSAFE_CHARS = re.compile(r'[:\[\]#^|\\*"<>?]')
WHITESPACE = re.compile(r"\s+")
FRONTMATTER_FENCE = "---"


class NoteExistsError(Exception):
    """A note for this Spotify episode link already exists; do not overwrite."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"episode note already exists: {path}")
        self.path = path


@dataclass(frozen=True)
class NoteNames:
    """The file names of one episode's note and its analysis note.

    Attributes:
        episode: ``YY-MM-DD Title.md``.
        analysis: ``YY-MM-DD Title - Analysis.md``.
    """

    episode: str
    analysis: str


def _date_prefix(published_at: date | None) -> str:
    """Return the note's ``YY-MM-DD`` prefix, today when the date is unknown."""
    return (published_at or date.today()).strftime("%y-%m-%d")


def _safe_name(value: str) -> str:
    """Strip Obsidian-unsafe characters and collapse whitespace."""
    cleaned = UNSAFE_CHARS.sub("", value).replace("/", "-")
    return WHITESPACE.sub(" ", cleaned).strip() or "Untitled"


def _frontmatter_value(path: Path, key: str) -> str | None:
    """Read one top-level frontmatter value from a note, None when absent."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return None
    for line in lines[1:]:
        if line.strip() == FRONTMATTER_FENCE:
            return None
        name, separator, value = line.partition(":")
        if separator and name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def _analysis_name(episode_name: str) -> str:
    """Return the analysis note name derived from a final episode note name."""
    return f"{Path(episode_name).stem} - Analysis.md"


def note_names(ref: EpisodeRef, show: str, *, output_dir: Path) -> NoteNames:
    """Return the episode and analysis note names, avoiding silent overwrites.

    The date-and-title name wins; when another episode holds it, the show
    name is appended, and when that is taken too the name is numbered. The
    analysis name is derived from the final episode stem, so both names
    carry the same suffix.

    Args:
        ref: The episode link and its metadata.
        show: Show name, used only in the clash names.
        output_dir: Folder that holds episode notes.

    Returns:
        The two note file names, without the folder.

    Raises:
        NoteExistsError: A note for the same Spotify URL already exists.
    """
    prefix = _date_prefix(ref.published_at)
    base = f"{prefix} {_safe_name(ref.episode_title)}.md"
    directory = Path(output_dir)
    target = directory / base
    if not target.exists():
        return NoteNames(base, _analysis_name(base))
    if _frontmatter_value(target, "spotify_url") == ref.spotify_url:
        raise NoteExistsError(target)
    stem = f"{prefix} {_safe_name(ref.episode_title)} - {_safe_name(show)}"
    for number in count(1):
        name = stem if number == 1 else f"{stem} {number}"
        path = directory / f"{name}.md"
        if not path.exists():
            return NoteNames(path.name, _analysis_name(path.name))
        if _frontmatter_value(path, "spotify_url") == ref.spotify_url:
            raise NoteExistsError(path)


def note_filename(ref: EpisodeRef, show: str, *, output_dir: Path) -> str:
    """Return the file name for an episode note, avoiding silent overwrites.

    Args:
        ref: The episode link and its metadata.
        show: Show name, used only in the clash names.
        output_dir: Folder that holds episode notes.

    Returns:
        The note file name, without the folder.

    Raises:
        NoteExistsError: A note for the same Spotify URL already exists.
    """
    return note_names(ref, show, output_dir=output_dir).episode


def _yaml_string(value: str) -> str:
    """Return a string as a YAML-safe double-quoted scalar."""
    return json.dumps(value, ensure_ascii=False)


def _wikilink(note_name: str) -> str:
    """Return an Obsidian wikilink to a note, without its ``.md`` suffix."""
    return f"[[{Path(note_name).stem}]]"


def _strip_analyzer_headers(text: str) -> str:
    """Drop ``CATEGORY:`` and ``FILENAME:`` header lines; a no-op otherwise."""
    lines = text.splitlines(keepends=True)
    return "".join(line for line in lines if not line.startswith(("CATEGORY:", "FILENAME:")))


def render_analysis_note(
    *,
    ref: EpisodeRef,
    analyzer: str,
    analysis: str,
    analyzed_at: datetime | None,
    episode_note: str,
) -> str:
    """Render one analysis note as Markdown: frontmatter and analyzer output.

    Args:
        ref: The episode link and its metadata.
        analyzer: Name of the analyzer that produced the analysis.
        analysis: The analyzer's Markdown, header lines stripped.
        analyzed_at: When the analysis was produced, None when unknown.
        episode_note: File name of the episode note to link back to.

    Returns:
        The complete Markdown document, ending in a newline.
    """
    published = ref.published_at.isoformat() if ref.published_at else "null"
    analyzed = _yaml_string(analyzed_at.isoformat(timespec="seconds")) if analyzed_at else "null"
    lines = [
        FRONTMATTER_FENCE,
        f"show: {_yaml_string(ref.show)}",
        f"episode: {_yaml_string(ref.episode_title)}",
        f"publish_date: {published}",
        f"spotify_url: {_yaml_string(ref.spotify_url)}",
        f"analyzer: {_yaml_string(analyzer)}",
        f"analyzed_at: {analyzed}",
        f"episode_note: {_yaml_string(_wikilink(episode_note))}",
        FRONTMATTER_FENCE,
    ]
    body = _strip_analyzer_headers(analysis).strip()
    return "\n".join([*lines, "", body]) + "\n"


def _frontmatter_lines(note: EpisodeNote, analysis_note: str | None = None) -> list[str]:
    """Render the note frontmatter, tags and cleanup status included."""
    ref = note.ref
    transcribed = note.transcript.transcribed_at
    published = ref.published_at.isoformat() if ref.published_at else "null"
    transcribed_text = _yaml_string(transcribed.isoformat(timespec="seconds")) if transcribed else "null"
    duration = note.duration_seconds if note.duration_seconds is not None else "null"
    lines = [
        FRONTMATTER_FENCE,
        f"show: {_yaml_string(ref.show)}",
        f"episode: {_yaml_string(ref.episode_title)}",
        f"publish_date: {published}",
        f"spotify_url: {_yaml_string(ref.spotify_url)}",
        f"feed_url: {_yaml_string(note.feed_url)}",
        f"duration: {duration}",
        f"language: {_yaml_string(note.transcript.language)}",
        f"speech_model: {_yaml_string(note.transcript.model)}",
        f"transcribed_at: {transcribed_text}",
    ]
    if analysis_note:
        lines.append(f"analysis_note: {_yaml_string(_wikilink(analysis_note))}")
    if note.tags:
        lines.append(f"tags: {json.dumps(list(note.tags), ensure_ascii=False)}")
    lines.extend([f"cleanup: {_yaml_string(note.cleanup)}", FRONTMATTER_FENCE])
    return lines


def render_episode_note(note: EpisodeNote, *, analysis_note: str | None = None) -> str:
    """Render one episode note as Markdown: frontmatter, summary, transcript.

    Sections for summary and key points are written only when the model holds
    them; the transcript always gets a heading.

    Args:
        note: Everything the note contains.
        analysis_note: File name of the analysis note to link, when there is one.

    Returns:
        The complete Markdown document, ending in a newline.
    """
    parts = ["\n".join(_frontmatter_lines(note, analysis_note)), ""]
    if note.summary:
        parts.extend(["## Summary", "", note.summary.strip(), ""])
    if note.key_points:
        points = "\n".join(f"- {point}" for point in note.key_points)
        parts.extend(["## Key points", "", points, ""])
    parts.extend(["## Transcript", ""])
    parts.extend(f"[{segment.timestamp}] {segment.text}" for segment in note.transcript.segments)
    return "\n".join(parts) + "\n"
