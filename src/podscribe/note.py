"""Render episode notes and choose their Obsidian-safe file names."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from podscribe.models import EpisodeRef

UNSAFE_CHARS = re.compile(r'[:\[\]#^|\\*"<>?]')
WHITESPACE = re.compile(r"\s+")
FRONTMATTER_FENCE = "---"


class NoteExistsError(Exception):
    """A note for this Spotify episode link already exists; do not overwrite."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"episode note already exists: {path}")
        self.path = path


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


def note_filename(ref: EpisodeRef, show: str, *, output_dir: Path) -> str:
    """Return the file name for an episode note, avoiding silent overwrites.

    A file for the same Spotify URL means the episode is already done.

    Args:
        ref: The episode link and its metadata.
        show: Show name, used only in the clash name.
        output_dir: Folder that holds episode notes.

    Returns:
        The note file name, without the folder.

    Raises:
        NoteExistsError: A note for the same Spotify URL already exists.
    """
    prefix = _date_prefix(ref.published_at)
    base = f"{prefix} {_safe_name(ref.episode_title)}.md"
    directory = Path(output_dir)
    target = directory / base
    if not target.exists():
        return base
    if _frontmatter_value(target, "spotify_url") == ref.spotify_url:
        raise NoteExistsError(target)
    alternate = f"{prefix} {_safe_name(ref.episode_title)} - {_safe_name(show)}.md"
    alternate_path = directory / alternate
    if alternate_path.exists() and _frontmatter_value(alternate_path, "spotify_url") == ref.spotify_url:
        raise NoteExistsError(alternate_path)
    return alternate
