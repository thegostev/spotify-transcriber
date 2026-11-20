"""Match a Spotify episode link to an item in the show's public feed."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, timezone
from email.utils import parsedate_to_datetime

from podscribe.models import EpisodeRef, FeedItem

DEFAULT_TOLERANCE_DAYS = 1


def _text(item: ET.Element, name: str) -> str:
    field = item.find(f"{{*}}{name}")
    return (field.text or "").strip() if field is not None else ""


def _published(item: ET.Element) -> date | None:
    raw = _text(item, "pubDate")
    if not raw:
        return None
    try:
        moment = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    return (moment.astimezone(timezone.utc) if moment.tzinfo else moment).date()


def _duration(item: ET.Element) -> int | None:
    raw = _text(item, "duration")
    if raw.isdigit():
        return int(raw)
    try:
        hours, minutes, seconds = (int(part) for part in raw.split(":"))
    except ValueError:
        return None
    return hours * 3600 + minutes * 60 + seconds


def _normalized(title: str) -> str:
    return " ".join(title.split()).casefold()


def match_feed_item(feed_xml: str, ref: EpisodeRef, *, tolerance_days: int = DEFAULT_TOLERANCE_DAYS) -> FeedItem | None:
    """Return the feed item that matches ``ref``.

    Args:
        feed_xml: The show's RSS feed document.
        ref: The episode link to match.
        tolerance_days: Accepted distance between the Spotify and feed dates.

    Returns:
        The matching item, or ``None`` when the episode is unmatched.
    """
    wanted = _normalized(ref.episode_title)
    best: tuple[int, ET.Element, date, str] | None = None
    for item in (node for node in ET.fromstring(feed_xml).iter() if node.tag.rsplit("}", 1)[-1] == "item"):
        if _normalized(_text(item, "title")) != wanted:
            continue
        published = _published(item)
        enclosure = item.find("{*}enclosure")
        audio_url = enclosure.get("url") if enclosure is not None else None
        if published is None or not audio_url:
            continue
        distance = 0 if ref.published_at is None else abs((published - ref.published_at).days)
        if distance <= tolerance_days and (best is None or distance < best[0]):
            best = (distance, item, published, audio_url)
    if best is None:
        return None
    _, item, published, audio_url = best
    return FeedItem(
        title=_text(item, "title"),
        published_at=published,
        audio_url=audio_url,
        duration_seconds=_duration(item),
        show_notes=_text(item, "description"),
        guid=_text(item, "guid") or None,
    )
