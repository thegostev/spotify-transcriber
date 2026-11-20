from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parents[1] / "fixtures"
SPOTIFY_PAGE = FIXTURES / "spotify_episode.html"


def test_parse_episode_page_reads_the_recorded_spotify_page():
    from podscribe.episode_page import parse_episode_page

    ref = parse_episode_page(SPOTIFY_PAGE.read_text(encoding="utf-8"))

    assert ref.spotify_url == "https://open.spotify.com/episode/34fjrBuyDwL9H6v2jfixFX"
    assert ref.show == "Huberman Lab"
    assert ref.episode_title == "Navigating Conflict, Finding Purpose & Maintaining Drive | Dr. Lex Fridman"
    assert ref.published_at == date(2022, 11, 28)


def test_parse_episode_page_unescapes_html_entities():
    from podscribe.episode_page import parse_episode_page

    html = """
    <html><head>
      <meta property="og:title" content="Bats &amp; Brains">
      <meta property="og:description" content="Night Show · Episode">
      <meta property="og:url" content="https://open.spotify.com/episode/abc">
      <meta name="music:release_date" content="2026-11-20T09:00:00Z">
    </head></html>
    """

    ref = parse_episode_page(html)

    assert ref.episode_title == "Bats & Brains"
    assert ref.show == "Night Show"
    assert ref.published_at == date(2026, 11, 20)


def test_parse_episode_page_leaves_publish_date_optional():
    from podscribe.episode_page import parse_episode_page

    html = """
    <meta property="og:title" content="Episode">
    <meta property="og:description" content="Show · Episode">
    <meta property="og:url" content="https://open.spotify.com/episode/abc">
    """

    assert parse_episode_page(html).published_at is None


def test_parse_episode_page_rejects_a_page_without_episode_metadata():
    from podscribe.episode_page import parse_episode_page

    with pytest.raises(ValueError):
        parse_episode_page("<html><head><title>Spotify – Web Player</title></head></html>")
