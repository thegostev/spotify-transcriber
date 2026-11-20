"""Failure notes and notifications for episode links that produced no note.

A failure note lives in the private docs root (``paths.failure_notes_dir``) and
records why an episode link produced no episode note: unmatched, download,
analyzer or write.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime
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


def _yaml_string(value: str) -> str:
    """Return a string as a YAML-safe double-quoted scalar."""
    return json.dumps(value, ensure_ascii=False)


def render_failure_note(
    *,
    ref: EpisodeRef,
    reason: str,
    occurred_at: datetime,
    log_tail: str | None,
    log_file: Path | None = None,
) -> str:
    """Render one failure note as Markdown: frontmatter and a reason body.

    Args:
        ref: The episode link and its metadata.
        reason: unmatched, download, analyzer or write.
        occurred_at: When the failure was recorded.
        log_tail: Trailing log lines, None when the log file is missing.
        log_file: The configured log path, named when the tail is missing.

    Returns:
        The complete Markdown document, ending in a newline.
    """
    stamp = occurred_at.isoformat(timespec="seconds")
    lines = [
        "---",
        f"show: {_yaml_string(ref.show)}",
        f"episode: {_yaml_string(ref.episode_title)}",
        f"spotify_url: {_yaml_string(ref.spotify_url)}",
        f"reason: {_yaml_string(reason)}",
        f"occurred_at: {_yaml_string(stamp)}",
        "---",
        "",
        f"# Failure: {ref.episode_title}",
        "",
        f"- Episode: [{ref.episode_title}]({ref.spotify_url})",
        f"- Show: {ref.show}",
        f"- Reason: {reason}",
        f"- Time: {stamp}",
        "",
        "## Last log lines",
        "",
    ]
    if log_tail is None:
        location = f"`{log_file}`" if log_file else "the configured log file"
        lines.append(f"No log file at {location}.")
    elif not log_tail.strip():
        location = f"`{log_file}`" if log_file else "the configured log file"
        lines.append(f"The log file is empty: {location}.")
    else:
        lines.extend(["```text", log_tail.rstrip("\n"), "```"])
    return "\n".join(lines) + "\n"
