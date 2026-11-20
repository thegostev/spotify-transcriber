from datetime import date


def test_segment_formats_timestamp_as_hh_mm_ss():
    from podscribe.models import Segment

    assert Segment(start_seconds=3725.9, text="hello").timestamp == "01:02:05"


def test_segment_timestamp_pads_single_digits():
    from podscribe.models import Segment

    assert Segment(start_seconds=7.4, text="intro").timestamp == "00:00:07"


def test_transcript_keeps_segments_language_and_model():
    from podscribe.models import Segment, Transcript

    segments = (Segment(start_seconds=0, text="a"), Segment(start_seconds=30, text="b"))
    transcript = Transcript(segments=segments, language="en", model="lfm3-audio")

    assert transcript.segments == segments
    assert transcript.language == "en"
    assert transcript.model == "lfm3-audio"


def test_transcript_defaults_to_plan1():
    from podscribe.models import Transcript

    transcript = Transcript(segments=(), language="en", model="lfm3-audio")

    assert transcript.plan == "plan1"
    assert transcript.transcribed_at is None


def test_episode_note_defaults_to_cleanup_done_and_no_summary():
    from podscribe.models import EpisodeNote, EpisodeRef, Transcript

    note = EpisodeNote(
        ref=EpisodeRef(spotify_url="https://open.spotify.com/episode/abc", show="S", episode_title="E"),
        feed_url="https://example/feed.xml",
        transcript=Transcript(segments=(), language="en", model="lfm3-audio"),
    )

    assert note.cleanup == "done"
    assert note.summary is None
    assert note.key_points == ()
    assert note.tags == ()
    assert note.duration_seconds is None


def test_episode_note_carries_feed_url_date_and_summary():
    from podscribe.models import EpisodeNote, EpisodeRef, Segment, Transcript

    ref = EpisodeRef(
        spotify_url="https://open.spotify.com/episode/abc",
        show="S",
        episode_title="E",
        published_at=date(2026, 11, 18),
    )
    note = EpisodeNote(
        ref=ref,
        feed_url="https://example/feed.xml",
        transcript=Transcript(segments=(Segment(0, "a"),), language="en", model="m"),
        duration_seconds=3725,
        summary="Five sentences.",
        key_points=("one", "two"),
        tags=("podcast", "learning"),
        cleanup="partial",
    )

    assert note.ref.published_at == date(2026, 11, 18)
    assert note.feed_url == "https://example/feed.xml"
    assert note.summary == "Five sentences."
    assert note.key_points == ("one", "two")
    assert note.tags == ("podcast", "learning")
    assert note.cleanup == "partial"
