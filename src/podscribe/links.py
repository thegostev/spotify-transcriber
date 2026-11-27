"""Canonical form of an episode link, so one episode is one queue job."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

EPISODE_PATH_MARKER = "/episode/"


def canonical_episode_url(url: str) -> str:
    """Return an episode link without its tracking parts.

    The queue keys on this form. ``?si=`` is a per-share tracking parameter, so
    two shares of one episode must not become two jobs.

    Args:
        url: An episode link as the user submitted it.

    Returns:
        The scheme and lowercased host, plus ``/episode/<id>`` when the path
        holds one, otherwise the path without its trailing slash. Query and
        fragment are dropped.
    """
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    marker = path.find(EPISODE_PATH_MARKER)
    if marker >= 0:
        episode_id = path[marker + len(EPISODE_PATH_MARKER) :].split("/", 1)[0]
        path = f"{EPISODE_PATH_MARKER}{episode_id}"
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, "", ""))
