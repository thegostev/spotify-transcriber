from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parents[1] / "fixtures"
SPOTIFY_PAGE = FIXTURES / "spotify_episode.html"
FEED_XML = (FIXTURES / "huberman_feed.xml").read_text(encoding="utf-8")
TARGET_TITLE = "Navigating Conflict, Finding Purpose & Maintaining Drive | Dr. Lex Fridman"

SIMPLE_FEED = """<?xml version="1.0"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Show</title>
    <item>
      <title>  A   Great   Episode </title>
      <pubDate>Mon, 28 Nov 2022 09:00:00 +0000</pubDate>
      <enclosure url="https://cdn.example/ep.mp3" type="audio/mpeg"/>
      <itunes:duration>1:02:03</itunes:duration>
      <guid>abc</guid>
    </item>
  </channel>
</rss>
"""


def test_match_feed_item_matches_the_recorded_episode():
    from podscribe.episode_page import parse_episode_page
    from podscribe.feed import match_feed_item

    ref = parse_episode_page(SPOTIFY_PAGE.read_text(encoding="utf-8"))

    item = match_feed_item(FEED_XML, ref, tolerance_days=1)

    assert item is not None
    assert item.title == TARGET_TITLE
    assert item.published_at == date(2022, 11, 28)
    assert item.audio_url == "https://traffic.megaphone.fm/SCIM7125421200.mp3?updated=1747806938"
    assert item.duration_seconds == 9400
    assert item.show_notes.startswith("My guest this episode is Lex Fridman")
    assert item.guid == "c131ee36-6dbd-11ed-9704-e3ecf342e2ab"


def test_match_feed_item_returns_none_for_an_unmatched_episode():
    from podscribe.feed import match_feed_item
    from podscribe.models import EpisodeRef

    ref = EpisodeRef(
        spotify_url="https://open.spotify.com/episode/abc",
        show="Huberman Lab",
        episode_title="A Spotify exclusive",
        published_at=date(2022, 11, 28),
    )

    assert match_feed_item(FEED_XML, ref, tolerance_days=1) is None


@pytest.mark.parametrize(
    ("published_at", "tolerance_days", "matched"),
    [
        (date(2022, 11, 27), 1, True),
        (date(2022, 11, 29), 1, True),
        (date(2022, 11, 30), 1, False),
        (date(2022, 11, 30), 2, True),
    ],
)
def test_match_feed_item_tolerates_dates_around_the_spotify_date(published_at, tolerance_days, matched):
    from podscribe.feed import match_feed_item
    from podscribe.models import EpisodeRef

    ref = EpisodeRef(
        spotify_url="https://open.spotify.com/episode/abc",
        show="Huberman Lab",
        episode_title=TARGET_TITLE,
        published_at=published_at,
    )

    assert (match_feed_item(FEED_XML, ref, tolerance_days=tolerance_days) is not None) is matched


def test_match_feed_item_falls_back_to_title_when_spotify_has_no_date():
    from podscribe.feed import match_feed_item
    from podscribe.models import EpisodeRef

    ref = EpisodeRef(
        spotify_url="https://open.spotify.com/episode/abc",
        show="Huberman Lab",
        episode_title=TARGET_TITLE,
    )

    item = match_feed_item(FEED_XML, ref, tolerance_days=1)

    assert item is not None
    assert item.published_at == date(2022, 11, 28)


def test_match_feed_item_parses_clock_style_durations_and_guid():
    from podscribe.feed import match_feed_item
    from podscribe.models import EpisodeRef

    ref = EpisodeRef(
        spotify_url="https://open.spotify.com/episode/abc",
        show="Show",
        episode_title="A Great Episode",
        published_at=date(2022, 11, 28),
    )

    item = match_feed_item(SIMPLE_FEED, ref, tolerance_days=0)

    assert item is not None
    assert item.duration_seconds == 3723
    assert item.guid == "abc"


def test_match_feed_item_skips_items_without_audio():
    from podscribe.feed import match_feed_item
    from podscribe.models import EpisodeRef

    feed = """<rss><channel><item>
      <title>Episode</title>
      <pubDate>Mon, 28 Nov 2022 09:00:00 +0000</pubDate>
    </item></channel></rss>"""
    ref = EpisodeRef(spotify_url="u", show="Show", episode_title="Episode", published_at=date(2022, 11, 28))

    assert match_feed_item(feed, ref, tolerance_days=1) is None
