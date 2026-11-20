"""Tests for Obsidian-safe episode note file names and name clashes."""

from datetime import date

import pytest

SPOTIFY_URL = "https://open.spotify.com/episode/abc"


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


def write_note(path, spotify_url):
    path.write_text(f'---\nshow: "S"\nspotify_url: "{spotify_url}"\n---\n\nbody\n', encoding="utf-8")


def test_note_filename_uses_publish_date_and_title(tmp_path):
    from podscribe.note import note_filename

    assert note_filename(ref(), "The Show", output_dir=tmp_path) == "26-11-18 An Episode.md"


def test_note_filename_strips_obsidian_unsafe_characters(tmp_path):
    from podscribe.note import note_filename

    title = 'A: B [C] #D ^ E | F \\ G * H "I" ? J <K> L'
    name = note_filename(ref(episode_title=title), "The Show", output_dir=tmp_path)

    assert name == "26-11-18 A B C D E F G H I J K L.md"


def test_note_filename_replaces_slashes_and_honours_today_without_date(tmp_path):
    from datetime import date as today_type

    from podscribe.note import note_filename

    name = note_filename(ref(episode_title="AC/DC live", published_at=None), "The Show", output_dir=tmp_path)

    assert name == f"{today_type.today():%y-%m-%d} AC-DC live.md"


def test_note_filename_adds_show_when_taken_by_another_episode(tmp_path):
    from podscribe.note import note_filename

    target = tmp_path / "26-11-18 An Episode.md"
    write_note(target, "https://open.spotify.com/episode/other")

    assert note_filename(ref(), "The Show", output_dir=tmp_path) == "26-11-18 An Episode - The Show.md"


def test_note_filename_signals_already_done_for_same_spotify_url(tmp_path):
    from podscribe.note import NoteExistsError, note_filename

    target = tmp_path / "26-11-18 An Episode.md"
    write_note(target, SPOTIFY_URL)

    with pytest.raises(NoteExistsError) as caught:
        note_filename(ref(), "The Show", output_dir=tmp_path)

    assert caught.value.path == target


def test_note_filename_sanitises_show_in_the_clash_name(tmp_path):
    from podscribe.note import note_filename

    target = tmp_path / "26-11-18 An Episode.md"
    write_note(target, "https://open.spotify.com/episode/other")

    assert note_filename(ref(), "The: Show", output_dir=tmp_path) == "26-11-18 An Episode - The Show.md"


@pytest.mark.xfail(strict=True, reason="LAG-1052")
def test_note_filename_numbers_when_the_show_name_is_also_taken(tmp_path):
    from podscribe.note import note_filename

    write_note(tmp_path / "26-11-18 An Episode.md", "https://open.spotify.com/episode/other")
    write_note(tmp_path / "26-11-18 An Episode - The Show.md", "https://open.spotify.com/episode/third")

    assert note_filename(ref(), "The Show", output_dir=tmp_path) == "26-11-18 An Episode - The Show 2.md"


@pytest.mark.xfail(strict=True, reason="LAG-1052")
def test_note_filename_signals_already_done_for_a_numbered_name(tmp_path):
    from podscribe.note import NoteExistsError, note_filename

    write_note(tmp_path / "26-11-18 An Episode.md", "https://open.spotify.com/episode/other")
    write_note(tmp_path / "26-11-18 An Episode - The Show.md", "https://open.spotify.com/episode/third")
    numbered = tmp_path / "26-11-18 An Episode - The Show 2.md"
    write_note(numbered, SPOTIFY_URL)

    with pytest.raises(NoteExistsError) as caught:
        note_filename(ref(), "The Show", output_dir=tmp_path)

    assert caught.value.path == numbered
