"""Render episode notes and choose their Obsidian-safe file names."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from itertools import count
from pathlib import Path

import yaml

from podscribe.models import EpisodeNote, EpisodeRef
from podscribe.names import NameFix

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


def safe_name(value: str) -> str:
    """Strip Obsidian-unsafe characters and collapse whitespace.

    Args:
        value: Any show or episode title.

    Returns:
        A file-name fragment that Obsidian accepts, ``Untitled`` when empty.
    """
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

    The date-and-title pair wins; when another episode holds it, the show
    name is appended, and when that is taken too the pair is numbered. The
    analysis name is derived from the final episode stem, so both names
    carry the same suffix. A pair is skipped when its episode note belongs
    to another link, or when only its analysis note exists for another link.
    An analysis note for the same link is reused: it is a leftover from a run
    whose episode note was never written.

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
    title = safe_name(ref.episode_title)
    base = f"{prefix} {title}.md"
    stem = f"{prefix} {title} - {safe_name(show)}"
    directory = Path(output_dir)
    for number in count():
        if number == 0:
            name = base
        elif number == 1:
            name = f"{stem}.md"
        else:
            name = f"{stem} {number}.md"
        episode = directory / name
        analysis = directory / _analysis_name(name)
        if episode.exists():
            if _frontmatter_value(episode, "spotify_url") == ref.spotify_url:
                raise NoteExistsError(episode)
            continue
        if analysis.exists() and _frontmatter_value(analysis, "spotify_url") != ref.spotify_url:
            continue
        return NoteNames(name, analysis.name)


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


def _missing_title(value: object) -> bool:
    """Return whether an analyzer title is absent or says it had no episode title."""
    return not isinstance(value, str) or not value.strip() or value.strip().lower().startswith("unknown")


def _split_leading_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Return a leading YAML block and the body after it.

    Analyzers may emit their own ``---`` block (the Podcast mode does: title,
    guest, host, topics). The note already has frontmatter, so the block is
    promoted into it and removed from the body. Text without a valid block is
    returned unchanged.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return {}, text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() != FRONTMATTER_FENCE:
            continue
        try:
            data = yaml.safe_load("".join(lines[1:index]))
        except yaml.YAMLError:
            return {}, text
        if isinstance(data, dict):
            return data, "".join(lines[index + 1 :])
        return {}, text
    return {}, text


def render_analysis_note(
    *,
    ref: EpisodeRef,
    analyzer: str,
    analysis: str,
    analyzed_at: datetime | None,
    episode_note: str,
    names: NameFix | None = None,
) -> str:
    """Render one analysis note as Markdown: frontmatter and analyzer output.

    Args:
        ref: The episode link and its metadata.
        analyzer: Name of the analyzer that produced the analysis.
        analysis: The analyzer's Markdown, header lines stripped.
        analyzed_at: When the analysis was produced, None when unknown.
        episode_note: File name of the episode note to link back to.
        names: Canonical guest and host; they win over the analyzer's block.

    Returns:
        The complete Markdown document, ending in a newline.
    """
    metadata, body_text = _split_leading_frontmatter(analysis)
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
    ]
    title = metadata.get("title")
    if names is not None and _missing_title(title):
        title = ref.episode_title
    if isinstance(title, str) and title.strip():
        lines.append(f"analyzer_title: {_yaml_string(title.strip())}")
    for field, canonical in (("guest", names and names.guest), ("host", names and names.host)):
        value = canonical or metadata.get(field)
        if isinstance(value, str) and value.strip():
            lines.append(f"{field}: {_yaml_string(value.strip())}")
    topics = metadata.get("topics")
    if isinstance(topics, list) and topics:
        lines.append(f"topics: {json.dumps([str(item) for item in topics], ensure_ascii=False)}")
    lines.extend([f"episode_note: {_yaml_string(_wikilink(episode_note))}", FRONTMATTER_FENCE])
    body = _strip_analyzer_headers(body_text).strip()
    return "\n".join([*lines, "", body]) + "\n"


def _frontmatter_lines(
    note: EpisodeNote, analysis_note: str | None = None, analyzer: str | None = None
) -> list[str]:
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
    ]
    if analyzer:
        lines.append(f"analyzer: {_yaml_string(analyzer)}")
    lines.append(f"transcribed_at: {transcribed_text}")
    if analysis_note:
        lines.append(f"analysis_note: {_yaml_string(_wikilink(analysis_note))}")
    if note.tags:
        lines.append(f"tags: {json.dumps(list(note.tags), ensure_ascii=False)}")
    lines.extend([f"cleanup: {_yaml_string(note.cleanup)}", FRONTMATTER_FENCE])
    return lines


def render_episode_note(
    note: EpisodeNote, *, analysis_note: str | None = None, analyzer: str | None = None
) -> str:
    """Render one episode note as Markdown: frontmatter, summary, transcript.

    Sections for summary and key points are written only when the model holds
    them; the transcript always gets a heading.

    Args:
        note: Everything the note contains.
        analysis_note: File name of the analysis note to link, when there is one.
        analyzer: Name of the analyzer that produced the transcript, when known.

    Returns:
        The complete Markdown document, ending in a newline.
    """
    parts = ["\n".join(_frontmatter_lines(note, analysis_note, analyzer)), ""]
    if note.summary:
        parts.extend(["## Summary", "", note.summary.strip(), ""])
    if note.key_points:
        points = "\n".join(f"- {point}" for point in note.key_points)
        parts.extend(["## Key points", "", points, ""])
    parts.extend(["## Transcript", ""])
    if note.transcript.timed:
        parts.extend(f"[{segment.timestamp}] {segment.text}" for segment in note.transcript.segments)
    else:
        parts.extend(segment.text for segment in note.transcript.segments)
    return "\n".join(parts) + "\n"
