"""Tests for failure notes: names, rendering and the log tail."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from podscribe.models import EpisodeRef

NOW = datetime(2026, 11, 20, 23, 30, 0)


def unsafe_ref() -> EpisodeRef:
    """Return an episode link whose title needs Obsidian-safe cleaning."""
    return EpisodeRef(
        spotify_url="https://open.spotify.com/episode/abc123",
        show="The: Show",
        episode_title='A: B [C] #D ^ E | F \\ G * H "I" ? J <K> L',
        published_at=date(2026, 11, 18),
    )


def test_failure_note_name_is_deterministic_and_obsidian_safe():
    from podscribe.failure import failure_note_name

    name = failure_note_name(unsafe_ref())

    assert name == "_Failed - A B C D E F G H I J K L.md"
    assert failure_note_name(unsafe_ref()) == name


@pytest.mark.parametrize("reason", ["unmatched", "download", "analyzer", "write"])
def test_render_failure_note_holds_the_required_fields(reason):
    from podscribe.failure import render_failure_note

    text = render_failure_note(
        ref=unsafe_ref(),
        reason=reason,
        occurred_at=NOW,
        log_tail="first line\nlast line",
        log_file=Path("/private/podscribe.log"),
    )

    frontmatter = yaml.safe_load(text.split("---", 2)[1])
    assert frontmatter == {
        "show": "The: Show",
        "episode": 'A: B [C] #D ^ E | F \\ G * H "I" ? J <K> L',
        "spotify_url": "https://open.spotify.com/episode/abc123",
        "reason": reason,
        "occurred_at": "2026-11-20T23:30:00",
    }
    body = text.split("---", 2)[2]
    assert "https://open.spotify.com/episode/abc123" in body
    assert "The: Show" in body
    assert reason in body
    assert "2026-11-20T23:30:00" in body
    assert "last line" in body


def test_render_failure_note_notes_a_missing_log_file():
    from podscribe.failure import render_failure_note

    text = render_failure_note(
        ref=unsafe_ref(), reason="unmatched", occurred_at=NOW, log_tail=None, log_file=Path("/private/missing.log")
    )

    assert "/private/missing.log" in text
    assert "No log file" in text


def test_read_log_tail_returns_the_last_twenty_lines(tmp_path):
    from podscribe.failure import read_log_tail

    log = tmp_path / "podscribe.log"
    log.write_text("\n".join(f"line {number}" for number in range(25)) + "\n", encoding="utf-8")

    tail = read_log_tail(log)

    assert tail is not None
    assert tail.splitlines() == [f"line {number}" for number in range(5, 25)]


def test_read_log_tail_returns_none_when_the_file_is_missing_or_empty(tmp_path):
    from podscribe.failure import read_log_tail

    assert read_log_tail(tmp_path / "missing.log") is None

    empty = tmp_path / "empty.log"
    empty.write_text("", encoding="utf-8")
    assert read_log_tail(empty) == ""


def test_write_failure_note_creates_the_private_directory(tmp_path):
    from podscribe.failure import failure_note_name, write_failure_note

    directory = tmp_path / "private" / "failures"
    log = tmp_path / "podscribe.log"
    log.write_text("started\nboom\n", encoding="utf-8")

    path = write_failure_note(
        unsafe_ref(), "download", directory=directory, occurred_at=NOW, log_file=log
    )

    assert path == directory / failure_note_name(unsafe_ref())
    text = path.read_text(encoding="utf-8")
    assert "boom" in text
    assert yaml.safe_load(text.split("---", 2)[1])["reason"] == "download"


def test_clear_failure_note_removes_only_the_expected_name(tmp_path):
    from podscribe.failure import clear_failure_note

    directory = tmp_path / "failures"
    directory.mkdir()
    expected = directory / "_Failed - A B C D E F G H I J K L.md"
    expected.write_text("failure\n", encoding="utf-8")
    other = directory / "_Failed - Another episode.md"
    other.write_text("keep\n", encoding="utf-8")

    assert clear_failure_note(unsafe_ref(), directory=directory) == expected
    assert not expected.exists()
    assert other.exists()
    assert clear_failure_note(unsafe_ref(), directory=directory) is None


def test_clear_failure_note_tolerates_a_missing_directory(tmp_path):
    from podscribe.failure import clear_failure_note

    assert clear_failure_note(unsafe_ref(), directory=tmp_path / "missing") is None


def test_notify_macos_runs_osascript_with_a_timeout():
    import subprocess

    from podscribe.failure import notify_macos

    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    notify_macos('podscribe failed', 'Show "X"\nline two', runner=runner)

    argv, kwargs = calls[0]
    assert argv[:2] == ["osascript", "-e"]
    assert "display notification" in argv[2]
    assert 'Show \\"X\\" line two' in argv[2]
    assert kwargs["timeout"] > 0


def test_notify_macos_swallows_runner_errors(capsys):
    from podscribe.failure import notify_macos

    def runner(argv, **kwargs):
        raise OSError("no osascript here")

    notify_macos("podscribe failed", "message", runner=runner)

    assert "notification failed" in capsys.readouterr().err
