import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

FIXTURES = Path(__file__).parents[1] / "fixtures"
ITUNES_SEARCH = FIXTURES / "itunes_search_huberman.json"

pytestmark = pytest.mark.xfail(strict=True, reason="LAG-1046")


class _FakeClient:
    """Return a canned JSON payload and record requested URLs."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def get_json(self, url: str) -> Any:
        self.urls.append(url)
        return self.payload


def test_find_feed_reads_the_recorded_itunes_search():
    from podscribe.itunes import find_feed

    payload = json.loads(ITUNES_SEARCH.read_text(encoding="utf-8"))
    client = _FakeClient(payload)

    assert find_feed("Huberman Lab", client) == "https://feeds.megaphone.fm/hubermanlab"


def test_find_feed_queries_itunes_for_podcasts():
    from podscribe.itunes import find_feed

    client = _FakeClient({"resultCount": 0, "results": []})

    find_feed("Huberman Lab", client)

    query = parse_qs(urlparse(client.urls[0]).query)
    assert query["term"] == ["Huberman Lab"]
    assert query["media"] == ["podcast"]
    assert query["entity"] == ["podcast"]
    assert query["country"] == ["US"]


def test_find_feed_prefers_an_exact_show_name():
    from podscribe.itunes import find_feed

    client = _FakeClient(
        {
            "resultCount": 2,
            "results": [
                {"collectionName": "Huberman Lab Recaps", "feedUrl": "https://example.test/recaps"},
                {"collectionName": "Huberman Lab", "feedUrl": "https://example.test/main"},
            ],
        }
    )

    assert find_feed("Huberman Lab", client) == "https://example.test/main"


def test_find_feed_returns_none_without_a_result_that_has_a_feed():
    from podscribe.itunes import find_feed

    client = _FakeClient({"resultCount": 1, "results": [{"collectionName": "Huberman Lab"}]})

    assert find_feed("Huberman Lab", client) is None
