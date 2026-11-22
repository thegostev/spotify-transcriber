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


def test_render_analysis_note_promotes_the_analyzer_metadata_block():
    from podscribe.note import render_analysis_note

    analysis = (
        "---\n"
        'title: "MCP: The Plumbing for AI Agents"\n'
        'guest: "Dan Delimarsky"\n'
        "topics: [mcp, ai-agents]\n"
        "---\n"
        "\n## TL;DR\n- One idea.\n"
    )

    text = render_analysis_note(
        ref=ref(),
        analyzer="superwhisper",
        analysis=analysis,
        analyzed_at=datetime(2026, 11, 20, 22, 0, 0),
        episode_note="26-11-18 An Episode.md",
    )

    assert 'analyzer_title: "MCP: The Plumbing for AI Agents"' in text
    assert 'guest: "Dan Delimarsky"' in text
    assert 'topics: ["mcp", "ai-agents"]' in text
    assert text.count("---") == 2
    assert text.endswith("## TL;DR\n- One idea.\n")


def test_render_analysis_note_prefers_the_canonical_names():
    from podscribe.names import NameFix
    from podscribe.note import render_analysis_note

    analysis = (
        "---\n"
        'guest: "Marcin Grzemski"\n'
        'host: "unknown"\n'
        "topics: [terraform]\n"
        "---\n"
        "\n## TL;DR\n- One idea.\n"
    )

    text = render_analysis_note(
        ref=ref(),
        analyzer="superwhisper",
        analysis=analysis,
        analyzed_at=None,
        episode_note="26-11-18 An Episode.md",
        names=NameFix(guest="Marcin Wyszynski", host="Lee Atchison"),
    )

    assert 'guest: "Marcin Wyszynski"' in text
    assert 'host: "Lee Atchison"' in text
    assert "Grzemski" not in text
    assert 'topics: ["terraform"]' in text


def test_render_analysis_note_replaces_an_unknown_analyzer_title():
    from podscribe.names import NameFix
    from podscribe.note import render_analysis_note

    analysis = "---\ntitle: \"unknown (episode title not provided)\"\n---\n\n## TL;DR\n- One idea.\n"

    text = render_analysis_note(
        ref=ref(),
        analyzer="superwhisper",
        analysis=analysis,
        analyzed_at=None,
        episode_note="26-11-18 An Episode.md",
        names=NameFix(),
    )

    assert 'analyzer_title: "An Episode"' in text
    assert "episode title not provided" not in text


@pytest.mark.xfail(strict=True, reason="LAG-1071")
def test_render_analysis_note_drops_a_malformed_analyzer_block():
    from podscribe.names import NameFix
    from podscribe.note import render_analysis_note

    analysis = (
        "---\n"
        'title: "{{EPISODE_TITLE}}"\n'
        'guest: "Marcin Wyszynski (spelled "Grzemski" in the transcript)"\n'
        "---\n"
        "\n## TL;DR\n- One idea.\n"
    )

    text = render_analysis_note(
        ref=ref(),
        analyzer="superwhisper",
        analysis=analysis,
        analyzed_at=None,
        episode_note="26-11-18 An Episode.md",
        names=NameFix(guest="Marcin Wyszynski", host="Lee Atchison"),
    )
    _, body = split_frontmatter(text)

    assert body.strip() == "## TL;DR\n- One idea."
    assert text.count("guest: ") == 1
    assert "{{EPISODE_TITLE}}" not in text
    assert 'analyzer_title: "An Episode"' in text


@pytest.mark.xfail(strict=True, reason="LAG-1071")
def test_render_analysis_note_replaces_a_placeholder_title():
    from podscribe.names import NameFix
    from podscribe.note import render_analysis_note

    analysis = '---\ntitle: "{{EPISODE_TITLE}}"\n---\n\n## TL;DR\n- One idea.\n'

    text = render_analysis_note(
        ref=ref(),
        analyzer="superwhisper",
        analysis=analysis,
        analyzed_at=None,
        episode_note="26-11-18 An Episode.md",
        names=NameFix(),
    )

    assert 'analyzer_title: "An Episode"' in text
    assert "{{EPISODE_TITLE}}" not in text
