import dataclasses
from datetime import date

import pytest

pytestmark = pytest.mark.xfail(strict=True, reason="LAG-1046")


def test_episode_ref_holds_link_show_and_title():
    from podscribe.models import EpisodeRef

    ref = EpisodeRef(
        spotify_url="https://open.spotify.com/episode/abc",
        show="The Show",
        episode_title="Episode one",
    )

    assert ref.spotify_url == "https://open.spotify.com/episode/abc"
    assert ref.show == "The Show"
    assert ref.episode_title == "Episode one"


def test_episode_ref_publish_date_is_optional():
    from podscribe.models import EpisodeRef

    without_date = EpisodeRef(spotify_url="u", show="s", episode_title="e")
    with_date = EpisodeRef(spotify_url="u", show="s", episode_title="e", published_at=date(2026, 11, 20))

    assert without_date.published_at is None
    assert with_date.published_at == date(2026, 11, 20)


def test_episode_ref_is_immutable():
    from podscribe.models import EpisodeRef

    ref = EpisodeRef(spotify_url="u", show="s", episode_title="e")

    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.show = "other"


def test_feed_item_carries_audio_url_and_duration():
    from podscribe.models import FeedItem

    item = FeedItem(
        title="Episode one",
        published_at=date(2026, 11, 18),
        audio_url="https://cdn.example/ep1.mp3",
        duration_seconds=3725,
        show_notes="Notes read by hand: Ada Lovelace, Grace Hopper.",
    )

    assert item.audio_url == "https://cdn.example/ep1.mp3"
    assert item.duration_seconds == 3725
    assert item.published_at == date(2026, 11, 18)


def test_feed_item_defaults_show_notes_and_guid():
    from podscribe.models import FeedItem

    item = FeedItem(title="t", published_at=date(2026, 11, 18), audio_url="a")

    assert item.show_notes == ""
    assert item.guid is None
    assert item.duration_seconds is None
