"""Tests for choosing episode and analysis note names as one pair."""

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


@pytest.mark.xfail(strict=True, reason="LAG-1052")
def test_note_names_pairs_episode_and_analysis_names(tmp_path):
    from podscribe.note import NoteNames, note_names

    assert note_names(ref(), "The Show", output_dir=tmp_path) == NoteNames(
        episode="26-11-18 An Episode.md",
        analysis="26-11-18 An Episode - Analysis.md",
    )


@pytest.mark.xfail(strict=True, reason="LAG-1052")
def test_note_names_derives_analysis_name_from_the_clashing_episode_stem(tmp_path):
    from podscribe.note import note_names

    write_note(tmp_path / "26-11-18 An Episode.md", "https://open.spotify.com/episode/other")

    names = note_names(ref(), "The Show", output_dir=tmp_path)

    assert names.episode == "26-11-18 An Episode - The Show.md"
    assert names.analysis == "26-11-18 An Episode - The Show - Analysis.md"


@pytest.mark.xfail(strict=True, reason="LAG-1052")
def test_note_names_numbers_both_names_together(tmp_path):
    from podscribe.note import note_names

    write_note(tmp_path / "26-11-18 An Episode.md", "https://open.spotify.com/episode/other")
    write_note(tmp_path / "26-11-18 An Episode - The Show.md", "https://open.spotify.com/episode/third")

    names = note_names(ref(), "The Show", output_dir=tmp_path)

    assert names.episode == "26-11-18 An Episode - The Show 2.md"
    assert names.analysis == "26-11-18 An Episode - The Show 2 - Analysis.md"


@pytest.mark.xfail(strict=True, reason="LAG-1052")
def test_note_names_signals_already_done_for_the_same_spotify_url(tmp_path):
    from podscribe.note import NoteExistsError, note_names

    target = tmp_path / "26-11-18 An Episode.md"
    write_note(target, SPOTIFY_URL)

    with pytest.raises(NoteExistsError) as caught:
        note_names(ref(), "The Show", output_dir=tmp_path)

    assert caught.value.path == target
