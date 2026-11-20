"""Read the public metadata of a Spotify episode page."""

from __future__ import annotations

from datetime import date
from html.parser import HTMLParser

from podscribe.models import EpisodeRef

DATE_PREFIX_LENGTH = 10


class _MetaTags(HTMLParser):
    """Collect meta tags and the canonical link from a page."""

    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.canonical: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record one opening tag."""
        values = dict(attrs)
        if tag == "meta":
            key = values.get("property") or values.get("name")
            content = values.get("content")
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag == "link" and values.get("rel") == "canonical":
            self.canonical = values.get("href")


def _release_date(raw: str | None) -> date | None:
    """Return the date part of an ISO 8601 release date."""
    if not raw:
        return None
    return date.fromisoformat(raw[:DATE_PREFIX_LENGTH])


def parse_episode_page(html: str) -> EpisodeRef:
    """Parse a Spotify episode page into an :class:`EpisodeRef`.

    Args:
        html: HTML of the public episode page.

    Returns:
        The episode link, show, title and publish date found in the page metadata.

    Raises:
        ValueError: When the page carries no episode title, show or link.
    """
    tags = _MetaTags()
    tags.feed(html)
    description = tags.meta.get("og:description", "")
    show = description.split(" · ")[0].strip() if " · " in description else ""
    title = tags.meta.get("og:title", "").strip()
    url = tags.meta.get("og:url") or tags.canonical
    if not title or not show or not url:
        raise ValueError("page has no Spotify episode metadata")
    return EpisodeRef(
        spotify_url=url,
        show=show,
        episode_title=title,
        published_at=_release_date(tags.meta.get("music:release_date")),
    )
