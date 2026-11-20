"""Tests for rendering the analysis note and linking it from the episode note."""

from datetime import date, datetime

import pytest

SPOTIFY_URL = "https://open.spotify.com/episode/abc"
ANALYSIS = "## Themes\n\nTrust and repair."


def ref(**overrides):
    from podscribe.models import EpisodeRef

    fields = {
        "spotify_url": SPOTIFY_URL,
        "show": "The Show",
        "episode_title": "An Episode",
        "published_at": date(2026, 11, 18),
    }
    fields.update(overrides)
    return EpisodeRef(**fields)


def make_note(**overrides):
    from podscribe.models import EpisodeNote, Transcript

    fields = {
        "ref": ref(),
        "feed_url": "https://example.com/feed.xml",
        "transcript": Transcript(segments=(), language="en", model="scribe"),
    }
    fields.update(overrides)
    return EpisodeNote(**fields)


def split_frontmatter(text):
    assert text.startswith("---\n")
    head, body = text[4:].split("\n---\n", 1)
    return head.splitlines(), body


@pytest.mark.xfail(strict=True, reason="LAG-1059")
def test_render_analysis_note_writes_frontmatter_and_links_the_episode_note():
    from podscribe.note import render_analysis_note

    text = render_analysis_note(
        ref=ref(),
        analyzer="superwhisper",
        analysis=ANALYSIS,
        analyzed_at=datetime(2026, 11, 18, 11, 0),
        episode_note="26-11-18 An Episode.md",
    )
    head, _ = split_frontmatter(text)

    assert head == [
        'show: "The Show"',
        'episode: "An Episode"',
        "publish_date: 2026-11-18",
        f'spotify_url: "{SPOTIFY_URL}"',
        'analyzer: "superwhisper"',
        'analyzed_at: "2026-11-18T11:00:00"',
        'episode_note: "[[26-11-18 An Episode]]"',
    ]


@pytest.mark.xfail(strict=True, reason="LAG-1059")
def test_render_analysis_note_keeps_the_podcast_mode_body_unchanged():
    from podscribe.note import render_analysis_note

    text = render_analysis_note(
        ref=ref(),
        analyzer="superwhisper",
        analysis=ANALYSIS,
        analyzed_at=None,
        episode_note="26-11-18 An Episode.md",
    )
    head, body = split_frontmatter(text)

    assert "analyzed_at: null" in head
    assert body.strip() == ANALYSIS
    assert text.endswith("\n")


@pytest.mark.xfail(strict=True, reason="LAG-1059")
def test_render_analysis_note_strips_category_and_filename_headers_when_present():
    from podscribe.note import render_analysis_note

    analysis = "CATEGORY: podcast\nFILENAME: episode\n\n## Themes\n\nBody"
    text = render_analysis_note(
        ref=ref(),
        analyzer="superwhisper",
        analysis=analysis,
        analyzed_at=None,
        episode_note="26-11-18 An Episode.md",
    )
    _, body = split_frontmatter(text)

    assert "CATEGORY:" not in body
    assert "FILENAME:" not in body
    assert body.strip() == "## Themes\n\nBody"


@pytest.mark.xfail(strict=True, reason="LAG-1059")
def test_render_episode_note_links_the_analysis_note_without_empty_sections():
    from podscribe.note import render_episode_note

    text = render_episode_note(make_note(), analysis_note="26-11-18 An Episode - Analysis.md")
    head, body = split_frontmatter(text)

    assert 'analysis_note: "[[26-11-18 An Episode - Analysis]]"' in head
    assert "## Summary" not in body
    assert "## Key points" not in body


def test_render_episode_note_omits_the_analysis_link_when_not_given():
    from podscribe.note import render_episode_note

    head, _ = split_frontmatter(render_episode_note(make_note()))

    assert not any(line.startswith("analysis_note:") for line in head)
