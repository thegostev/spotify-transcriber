"""Canonical names for an analysis, taken from the episode and feed metadata.

Superwhisper substitutes no metadata into a Custom Mode prompt, so the analyzer
never sees the episode title or the feed's author and copies the speech
engine's spelling of names. This module recovers the canonical guest, host and
brand from those sources and rewrites the spellings in the analyzer's Markdown.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

TITLE_GUEST_MARKER = " with "
TITLE_BRAND_SEPARATOR = ", "
MAX_NAME_WORDS = 4
SENTENCE_PUNCTUATION = (".", "!", "?", ":")
UNKNOWN_LABEL = re.compile(r"(?im)^(\s*(?:[-*]\s*)?\*\*(Guest|Host):\*\*)\s*unknown\b.*$")
QUOTED_SPAN = re.compile(r'("[^"]*"|“[^”]*”)')
TRANSCRIPT_CITED = re.compile(r"transcript|transcribed", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class NameFix:
    """Canonical names and spelling corrections for one analysis.

    Attributes:
        guest: Guest name from the episode title or config; empty when unknown.
        host: Host name from the feed's ``itunes:author`` or config.
        brand: Brand from the title or config, in its canonical spelling.
        aliases: Wrong -> right spellings, in config order.
    """

    guest: str = ""
    host: str = ""
    brand: str = ""
    aliases: tuple[tuple[str, str], ...] = ()


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


def _aliases(value: object) -> tuple[tuple[str, str], ...]:
    """Return the configured wrong -> right spelling pairs."""
    if not isinstance(value, Mapping):
        return ()
    pairs = ((str(wrong).strip(), str(right).strip()) for wrong, right in value.items())
    return tuple((wrong, right) for wrong, right in pairs if wrong and right)


def derive_names(episode_title: str, author: str = "", rules: Mapping[str, Any] | None = None) -> NameFix:
    """Return the canonical names for one episode.

    Args:
        episode_title: The title as Spotify shows it.
        author: The feed's channel ``itunes:author``.
        rules: Optional ``analysis.names`` config: ``guest``, ``host`` and
            ``brand`` overrides plus an ``aliases`` wrong -> right mapping.

    Returns:
        The names to write, with config overrides taking precedence.
    """
    settings = rules if isinstance(rules, Mapping) else {}
    guest, brand = _from_title(episode_title)
    return NameFix(
        guest=_text(settings.get("guest")) or guest,
        host=_text(settings.get("host")) or author.strip(),
        brand=_text(settings.get("brand") or brand),
        aliases=_aliases(settings.get("aliases")),
    )


def _replace_unknown_labels(text: str, fix: NameFix) -> str:
    """Write the canonical name where the analysis says a role is unknown."""
    names = {"guest": fix.guest, "host": fix.host}

    def swap(match: re.Match[str]) -> str:
        name = names[match.group(2).lower()]
        return f"{match.group(1)} {name}." if name else match.group(0)

    return UNKNOWN_LABEL.sub(swap, text)


def _replace_names(text: str, fix: NameFix) -> str:
    """Replace alias and brand spellings everywhere in one span of text."""
    for wrong, right in fix.aliases:
        text = text.replace(wrong, right)
    if fix.brand:
        pattern = re.compile(rf"\b{re.escape(fix.brand)}\b", re.IGNORECASE)
        text = pattern.sub(lambda _: fix.brand, text)
    return text


def _correct_line(line: str, fix: NameFix) -> str:
    """Correct one line, keeping the spellings it cites as the transcript's.

    Quoted text is corrected too, unless the line reports what the transcript
    said or the quote is the source half of a ``"wrong" -> "right"`` entry.
    """
    cites_transcript = bool(TRANSCRIPT_CITED.search(line))
    parts = QUOTED_SPAN.split(line)
    for index in range(len(parts)):
        quoted = index % 2 == 1
        followed_by_arrow = index + 1 < len(parts) and parts[index + 1].lstrip().startswith(("->", "\u2192"))
        if not quoted or not (cites_transcript or followed_by_arrow):
            parts[index] = _replace_names(parts[index], fix)
    return "".join(parts)


def correct_analysis(text: str, fix: NameFix) -> str:
    """Return ``text`` with known wrong spellings and brand casing fixed.

    Corrections reach direct quotes too, because the speech engine misspells
    names there. Two cited spellings stay as they are: what the analysis says
    the transcript showed, and the source half of a ``"wrong" -> "right"``
    entry.

    Args:
        text: The analyzer's Markdown.
        fix: The canonical names for this episode.

    Returns:
        The Markdown with every alias and non-canonical brand spelling replaced,
        and every "unknown" guest or host label named.
    """
    corrected = "".join(_correct_line(line, fix) for line in text.splitlines(keepends=True))
    return _replace_unknown_labels(corrected, fix)
