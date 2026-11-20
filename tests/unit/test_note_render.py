"""Tests for rendering an EpisodeNote to Markdown."""

from datetime import date, datetime

SPOTIFY_URL = "https://open.spotify.com/episode/abc"
FEED_URL = "https://example.com/feed.xml"


def make_note(**overrides):
    from podscribe.models import EpisodeNote, EpisodeRef, Segment, Transcript

    fields = {
        "ref": EpisodeRef(
            spotify_url=SPOTIFY_URL,
            show="The Show",
            episode_title="An Episode",
            published_at=date(2026, 11, 18),
        ),
        "feed_url": FEED_URL,
        "transcript": Transcript(
            segments=(Segment(0, "hello"), Segment(3725.9, "world")),
            language="en",
            model="lfm3-audio",
            transcribed_at=datetime(2026, 11, 18, 10, 30),
        ),
        "duration_seconds": 3725,
    }
    fields.update(overrides)
    return EpisodeNote(**fields)


def split_frontmatter(text):
    assert text.startswith("---\n")
    head, body = text[4:].split("\n---\n", 1)
    return head.splitlines(), body


def test_render_episode_note_writes_the_expected_frontmatter():
    from podscribe.note import render_episode_note

    head, _ = split_frontmatter(render_episode_note(make_note()))

    assert head == [
        'show: "The Show"',
        'episode: "An Episode"',
        "publish_date: 2026-11-18",
        f'spotify_url: "{SPOTIFY_URL}"',
        f'feed_url: "{FEED_URL}"',
        "duration: 3725",
        'language: "en"',
        'speech_model: "lfm3-audio"',
        'transcribed_at: "2026-11-18T10:30:00"',
        'cleanup: "done"',
    ]


def test_render_episode_note_writes_transcript_lines():
    from podscribe.note import render_episode_note

    _, body = split_frontmatter(render_episode_note(make_note()))

    assert "## Transcript" in body
    assert "[00:00:00] hello" in body
    assert "[01:02:05] world" in body


def test_render_episode_note_renders_summary_and_key_points():
    from podscribe.note import render_episode_note

    _, body = split_frontmatter(
        render_episode_note(make_note(summary="Five sentences.", key_points=("one", "two")))
    )

    assert "## Summary\n\nFive sentences." in body
    assert "## Key points\n\n- one\n- two" in body
    assert body.index("## Summary") < body.index("## Key points") < body.index("## Transcript")


def test_render_episode_note_renders_tags_and_cleanup_when_present():
    from podscribe.note import render_episode_note

    head, _ = split_frontmatter(
        render_episode_note(make_note(tags=("podcast", "learning"), cleanup="partial"))
    )

    assert 'tags: ["podcast", "learning"]' in head
    assert 'cleanup: "partial"' in head


def test_render_episode_note_omits_absent_summary_tags_and_unknown_values():
    from podscribe.models import EpisodeRef, Transcript
    from podscribe.note import render_episode_note

    note = make_note(
        ref=EpisodeRef(spotify_url=SPOTIFY_URL, show="S", episode_title="E", published_at=None),
        transcript=Transcript(segments=(), language="en", model="m"),
        duration_seconds=None,
    )
    head, body = split_frontmatter(render_episode_note(note))

    assert "## Summary" not in body
    assert "## Key points" not in body
    assert not any(line.startswith("tags:") for line in head)
    assert "publish_date: null" in head
    assert "duration: null" in head
    assert "transcribed_at: null" in head
    assert "[0" not in body


def test_render_episode_note_escapes_quotes_in_yaml():
    from podscribe.models import EpisodeRef
    from podscribe.note import render_episode_note

    ref = EpisodeRef(spotify_url=SPOTIFY_URL, show='He said "hi"', episode_title="E")
    head, _ = split_frontmatter(render_episode_note(make_note(ref=ref)))

    assert 'show: "He said \\"hi\\""' in head
