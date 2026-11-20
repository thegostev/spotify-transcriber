"""Find a show's public feed through the iTunes Search API."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from podscribe.http import HttpClientLike

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
SEARCH_LIMIT = 5


def _feed_url(result: dict[str, Any]) -> str | None:
    """Return a result's feed URL when it has one."""
    feed_url = result.get("feedUrl")
    return str(feed_url) if feed_url else None


def _names(result: dict[str, Any]) -> set[str]:
    """Return the result's show names, casefolded."""
    return {str(result.get(key, "")).casefold() for key in ("collectionName", "trackName")}


def find_feed(
    show: str,
    client: HttpClientLike,
    *,
    country: str = "US",
    search_url: str = ITUNES_SEARCH_URL,
) -> str | None:
    """Return the public feed URL for ``show``.

    Args:
        show: Show name as it appears on the Spotify page.
        client: HTTP client used for the search request.
        country: iTunes storefront to search.
        search_url: iTunes Search endpoint; overridable from config later.

    Returns:
        The feed URL of the best result, or ``None`` when iTunes has no match.
    """
    query = urlencode(
        {"term": show.strip(), "media": "podcast", "entity": "podcast", "limit": SEARCH_LIMIT, "country": country}
    )
    payload = client.get_json(f"{search_url}?{query}")
    results = payload.get("results", []) if isinstance(payload, dict) else []
    candidates = [result for result in results if isinstance(result, dict) and _feed_url(result)]
    wanted = show.strip().casefold()
    for result in candidates:
        if wanted in _names(result):
            return _feed_url(result)
    return _feed_url(candidates[0]) if candidates else None
