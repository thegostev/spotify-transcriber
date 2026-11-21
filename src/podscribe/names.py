"""Canonical names for an analysis, taken from the episode and feed metadata.

Superwhisper substitutes no metadata into a Custom Mode prompt, so the analyzer
never sees the episode title or the feed's author and copies the speech
engine's spelling of names. This module recovers the canonical guest, host and
brand from those sources and rewrites the spellings in the analyzer's Markdown.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

TITLE_GUEST_MARKER = " with "
TITLE_BRAND_SEPARATOR = ", "
MAX_NAME_WORDS = 4
SENTENCE_PUNCTUATION = (".", "!", "?", ":")


@dataclass(frozen=True, slots=True)
class NameFix:
    """Canonical names and spelling corrections for one analysis.

    Attributes:
        guest: Guest name from the episode title or config; empty when unknown.
        host: Host name from the feed's ``itunes:author`` or config.
        brand: Brand from the title or config, in its canonical spelling.
    """

    guest: str = ""
    host: str = ""
    brand: str = ""


def _text(value: object) -> str:
    """Return a stripped string for a config value, empty for anything else."""
    return value.strip() if isinstance(value, str) else ""


def _looks_like_name(value: str) -> bool:
    """Return whether ``value`` reads as a name or brand, not a sentence."""
    return bool(value.split()) and len(value.split()) <= MAX_NAME_WORDS and not value.endswith(SENTENCE_PUNCTUATION)


def _from_title(title: str) -> tuple[str, str]:
    """Return ``(guest, brand)`` from a title shaped ``<topic> with <Guest>, <Brand>``."""
    _, marker, tail = title.rpartition(TITLE_GUEST_MARKER)
    if not marker:
        return "", ""
    guest, separator, brand = tail.rpartition(TITLE_BRAND_SEPARATOR)
    if not separator:
        return (tail.strip(), "") if _looks_like_name(tail) else ("", "")
    if not _looks_like_name(guest):
        return "", ""
    return guest.strip(), brand.strip() if _looks_like_name(brand) else ""


def derive_names(episode_title: str, author: str = "", rules: Mapping[str, Any] | None = None) -> NameFix:
    """Return the canonical names for one episode.

    Args:
        episode_title: The title as Spotify shows it.
        author: The feed's channel ``itunes:author``.
        rules: Optional ``analysis.names`` config: ``guest``, ``host`` and
            ``brand`` overrides.

    Returns:
        The names to write, with config overrides taking precedence.
    """
    settings = rules or {}
    guest, brand = _from_title(episode_title)
    return NameFix(
        guest=_text(settings.get("guest")) or guest,
        host=_text(settings.get("host")) or author.strip(),
        brand=_text(settings.get("brand") or brand),
    )
