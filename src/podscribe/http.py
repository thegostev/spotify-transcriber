"""HTTP access for podscribe - the only module that opens a network socket.

Every external request (Spotify page, iTunes Search, feed, audio) goes through
this client so tests can substitute a fixture-backed implementation.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Protocol

DEFAULT_USER_AGENT = "podscribe/0.0.0"
DEFAULT_TIMEOUT_SECONDS = 30.0
CHUNK_SIZE = 64 * 1024


class HttpClientLike(Protocol):
    """The operations the pipeline needs from an HTTP client."""

    def get_text(self, url: str) -> str:
        """Return the response body for ``url`` as text."""
    def get_json(self, url: str) -> Any:
        """Return the JSON-decoded response body for ``url``."""
    def download(self, url: str, destination: Path) -> Path:
        """Stream the response body for ``url`` into ``destination``."""


class HttpClient:
    """A small urllib client; construct one and pass it to the intake steps."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Configure the client.

        Args:
            user_agent: User-Agent header sent with every request.
            timeout: Socket timeout in seconds.
        """
        self._user_agent = user_agent
        self._timeout = timeout

    def _open(self, url: str):
        """Return the open response for ``url``."""
        request = urllib.request.Request(url, headers={"User-Agent": self._user_agent})
        return urllib.request.urlopen(request, timeout=self._timeout)

    def get_bytes(self, url: str) -> bytes:
        """Return the raw response body for ``url``."""
        with self._open(url) as response:
            return response.read()

    def get_text(self, url: str, *, encoding: str = "utf-8") -> str:
        """Return the response body for ``url`` decoded as text."""
        return self.get_bytes(url).decode(encoding)

    def get_json(self, url: str) -> Any:
        """Return the JSON-decoded response body for ``url``."""
        return json.loads(self.get_text(url))

    def download(self, url: str, destination: Path) -> Path:
        """Stream the response body for ``url`` into ``destination``.

        Args:
            url: Enclosure URL to fetch.
            destination: File path to create; parent directories are created.

        Returns:
            The path written.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._open(url) as response, destination.open("wb") as sink:
            while chunk := response.read(CHUNK_SIZE):
                sink.write(chunk)
        return destination
