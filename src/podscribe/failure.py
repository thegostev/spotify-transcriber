"""Failure notes and notifications for episode links that produced no note.

A failure note lives in the private docs root (``paths.failure_notes_dir``) and
records why an episode link produced no episode note: unmatched, download,
analyzer or write.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from podscribe.models import EpisodeRef
from podscribe.note import safe_name

FAILURE_PREFIX = "_Failed - "
LOG_TAIL_LINES = 20


def failure_note_name(ref: EpisodeRef) -> str:
    """Return the deterministic Obsidian-safe failure note name.

    Args:
        ref: The episode link and its metadata.

    Returns:
        ``_Failed - <episode title>.md`` with unsafe characters stripped.
    """
    return f"{FAILURE_PREFIX}{safe_name(ref.episode_title)}.md"


def failure_note_path(ref: EpisodeRef, *, directory: Path | str) -> Path:
    """Return the failure note path inside the private docs root.

    Args:
        ref: The episode link and its metadata.
        directory: The configured ``paths.failure_notes_dir``.

    Returns:
        The path the note would be written to.
    """
    return Path(directory) / failure_note_name(ref)


def read_log_tail(path: Path | str | None, *, max_lines: int = LOG_TAIL_LINES) -> str | None:
    """Return the trailing lines of the log file, None when it is unreadable.

    Args:
        path: The configured ``paths.log_file``, or None when unknown.
        max_lines: How many trailing lines to keep.

    Returns:
        The tail without its final newline; ``""`` for an empty file and
        ``None`` when the file is missing or cannot be read.
    """
    if path is None:
        return None
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as handle:
            lines = deque(handle, maxlen=max_lines)
    except OSError:
        return None
    return "".join(lines).rstrip("\n")
