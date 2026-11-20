"""Tests for the `podscribe add` pipeline: link -> feed -> audio -> notes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from podscribe.analyzer import AnalyzerResult
from podscribe.config import Config
from podscribe.models import EpisodeRef, Segment, Transcript

SPOTIFY_HTML = """
<html><head>
  <meta property="og:title" content="MCP, CLIs and agents">
  <meta property="og:description" content="Talk Python To Me · Episode">
  <meta property="og:url" content="https://open.spotify.com/episode/abc123">
  <meta name="music:release_date" content="2026-10-15T00:00:00Z">
</head></html>
"""

ITUNES_JSON = {
    "results": [
        {
            "collectionName": "Talk Python To Me",
            "trackName": "Talk Python To Me",
            "feedUrl": "https://feeds.example/talkpython",
        }
    ]
}

FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Talk Python To Me</title>
    <item>
      <title>MCP, CLIs and agents</title>
      <pubDate>Thu, 15 Oct 2026 00:00:00 GMT</pubDate>
      <itunes:duration>00:10:00</itunes:duration>
      <enclosure url="https://cdn.example/tp569.mp3" type="audio/mpeg" length="1"/>
    </item>
  </channel>
</rss>
"""


class FakeClient:
    """Serve the three intake responses and write a stand-in audio file."""

    def __init__(self) -> None:
        self.downloads: list[str] = []

    def get_text(self, url: str) -> str:
        if url == "https://open.spotify.com/episode/abc123":
            return SPOTIFY_HTML
        if url == "https://feeds.example/talkpython":
            return FEED_XML
        raise AssertionError(f"unexpected URL {url}")

    def get_json(self, url: str):
        assert url.startswith("https://itunes.example/search")
        return ITUNES_JSON

    def download(self, url: str, destination: Path) -> Path:
        self.downloads.append(url)
        destination.write_bytes(b"ID3 fake audio")
        return destination


class FakeAnalyzer:
    """Return a fixed result and remember the audio path it was given."""

    def __init__(self) -> None:
        self.audio: Path | None = None

    def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
        self.audio = audio
        transcript = Transcript(
            segments=(Segment(start_seconds=0.0, text="Hello and welcome."),),
            language="en",
            model="Podcast",
            transcribed_at=datetime(2026, 11, 20, 22, 0, 0),
        )
        return AnalyzerResult(transcript=transcript, analysis="## TL;DR\n- One idea.", analyzer="command")


def make_config(tmp_path: Path, *, output: Path | None = None, macos: bool = False) -> Config:
    """Build a Config with temp paths, no real filesystem or network."""
    output_dir = output or tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        paths={
            "output_dir": str(output_dir),
            "failure_notes_dir": str(tmp_path / "failures"),
            "data_dir": str(tmp_path / "data"),
            "log_file": str(tmp_path / "data" / "podscribe.log"),
        },
        intake={
            "itunes_search_url": "https://itunes.example/search",
            "match_window_days": 2,
            "user_agent": "podscribe-test",
        },
        analyzer={"backend": "command", "command": {"argv": ["fake"]}},
        speech={},
        llm={},
        notifications={"macos": macos},
        remote={"transport": "rex", "rex_host": "mini", "rex_session": "p", "ssh_target": "h@m"},
        source=tmp_path / "config.yaml",
    )


def test_add_episode_dry_run_resolves_without_download_or_write(tmp_path):
    from podscribe.cli import add_episode

    client = FakeClient()
    outcome = add_episode(
        "https://open.spotify.com/episode/abc123",
        make_config(tmp_path),
        client=client,
        analyzer=FakeAnalyzer(),
        dry_run=True,
    )

    assert outcome.status == "planned"
    assert outcome.episode_note is not None
    assert outcome.episode_note.name == "26-10-15 MCP, CLIs and agents.md"
    assert not outcome.episode_note.exists()
    assert client.downloads == []


def test_add_episode_writes_episode_and_analysis_notes(tmp_path):
    from podscribe.cli import add_episode

    client = FakeClient()
    analyzer = FakeAnalyzer()
    config = make_config(tmp_path)

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123", config, client=client, analyzer=analyzer, dry_run=False
    )

    assert outcome.status == "done"
    assert analyzer.audio is not None and analyzer.audio.exists()
    assert client.downloads == ["https://cdn.example/tp569.mp3"]
    episode = outcome.episode_note.read_text(encoding="utf-8")
    analysis = outcome.analysis_note.read_text(encoding="utf-8")
    assert 'show: "Talk Python To Me"' in episode
    assert "publish_date: 2026-10-15" in episode
    assert 'analyzer: "command"' in episode
    assert "[00:00:00] Hello and welcome." in episode
    assert 'episode_note: "[[26-10-15 MCP, CLIs and agents]]"' in analysis
    assert "## TL;DR" in analysis


def test_add_episode_without_analysis_writes_one_note(tmp_path):
    from podscribe.cli import add_episode

    class NoAnalysisAnalyzer(FakeAnalyzer):
        def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
            result = super().analyze(audio, ref)
            return AnalyzerResult(transcript=result.transcript, analysis=None, analyzer="command")

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123",
        make_config(tmp_path),
        client=FakeClient(),
        analyzer=NoAnalysisAnalyzer(),
        dry_run=False,
    )

    assert outcome.status == "done"
    assert outcome.analysis_note is None
    assert outcome.episode_note.exists()
    assert list(outcome.episode_note.parent.glob("*Analysis*")) == []


def test_add_episode_reports_an_unmatched_episode(tmp_path):
    from podscribe.cli import add_episode

    class WrongTitleClient(FakeClient):
        def get_text(self, url: str) -> str:
            return super().get_text(url).replace("MCP, CLIs and agents</title>", "Another episode</title>")

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123",
        make_config(tmp_path),
        client=WrongTitleClient(),
        analyzer=FakeAnalyzer(),
        dry_run=False,
    )

    assert outcome.status == "unmatched"
    assert outcome.episode_note is None


def _write_config(tmp_path: Path) -> Path:
    """Write a config.yaml that load_config accepts, with temp paths."""
    import yaml

    config = make_config(tmp_path)
    data = {
        "paths": config.paths,
        "intake": config.intake,
        "analyzer": config.analyzer,
        "notifications": config.notifications,
        "remote": config.remote,
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_main_dry_run_prints_the_target_path(tmp_path, capsys):
    from podscribe.cli import main

    exit_code = main(
        ["add", "https://open.spotify.com/episode/abc123", "--dry-run", "--config", str(_write_config(tmp_path))],
        client=FakeClient(),
        analyzer=FakeAnalyzer(),
    )

    assert exit_code == 0
    assert "26-10-15 MCP, CLIs and agents.md" in capsys.readouterr().out


def test_add_episode_fills_a_missing_transcribed_at(tmp_path):
    from podscribe.cli import add_episode

    class UntimedAnalyzer(FakeAnalyzer):
        def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
            result = super().analyze(audio, ref)
            transcript = Transcript(segments=result.transcript.segments, language="en", model="Podcast")
            return AnalyzerResult(transcript=transcript, analysis=None, analyzer="command")

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123",
        make_config(tmp_path),
        client=FakeClient(),
        analyzer=UntimedAnalyzer(),
        dry_run=False,
        now=datetime(2026, 11, 20, 23, 0, 0),
    )

    assert 'transcribed_at: "2026-11-20T23:00:00"' in outcome.episode_note.read_text(encoding="utf-8")


class WrongTitleClient(FakeClient):
    """Serve a feed whose item title does not match the episode."""

    def get_text(self, url: str) -> str:
        return super().get_text(url).replace("MCP, CLIs and agents</title>", "Another episode</title>")


class NoFeedClient(FakeClient):
    """Serve an iTunes search without a result."""

    def get_json(self, url: str):
        return {"results": []}


class FailingDownloadClient(FakeClient):
    """Fail while writing the audio file."""

    def download(self, url: str, destination: Path) -> Path:
        raise OSError("disk full")


class FailingAnalyzer(FakeAnalyzer):
    """Fail while analyzing the audio."""

    def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
        from podscribe.analyzer import AnalyzerError

        raise AnalyzerError("analyzer exploded")


def test_add_episode_unmatched_writes_failure_note_and_no_episode_note(tmp_path):
    from podscribe.cli import add_episode

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123",
        make_config(tmp_path),
        client=WrongTitleClient(),
        analyzer=FakeAnalyzer(),
    )

    assert outcome.status == "unmatched"
    assert outcome.reason == "unmatched"
    assert outcome.episode_note is None
    assert outcome.failure_note is not None
    assert outcome.failure_note.name == "_Failed - MCP, CLIs and agents.md"
    assert "unmatched" in outcome.failure_note.read_text(encoding="utf-8")
    assert list((tmp_path / "out").glob("*.md")) == []


def test_add_episode_without_a_feed_writes_an_unmatched_failure_note(tmp_path):
    from podscribe.cli import add_episode

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123",
        make_config(tmp_path),
        client=NoFeedClient(),
        analyzer=FakeAnalyzer(),
    )

    assert outcome.status == "no_feed"
    assert outcome.reason == "unmatched"
    assert outcome.failure_note is not None
    assert outcome.failure_note.exists()
    assert outcome.episode_note is None


def test_add_episode_download_error_writes_a_failure_note(tmp_path):
    from podscribe.cli import add_episode

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123",
        make_config(tmp_path),
        client=FailingDownloadClient(),
        analyzer=FakeAnalyzer(),
    )

    assert outcome.status == "failed"
    assert outcome.reason == "download"
    assert outcome.failure_note is not None
    assert "download" in outcome.failure_note.read_text(encoding="utf-8")
    assert list((tmp_path / "out").glob("*.md")) == []


def test_add_episode_analyzer_error_writes_a_failure_note(tmp_path):
    from podscribe.cli import add_episode

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123",
        make_config(tmp_path),
        client=FakeClient(),
        analyzer=FailingAnalyzer(),
    )

    assert outcome.status == "failed"
    assert outcome.reason == "analyzer"
    assert outcome.failure_note is not None
    assert "analyzer" in outcome.failure_note.read_text(encoding="utf-8")


def test_add_episode_write_error_writes_a_failure_note(tmp_path):
    from podscribe.cli import add_episode

    config = make_config(tmp_path)
    output = Path(config.paths["output_dir"])
    output.rmdir()
    output.write_text("not a directory", encoding="utf-8")

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123", config, client=FakeClient(), analyzer=FakeAnalyzer()
    )

    assert outcome.status == "failed"
    assert outcome.reason == "write"
    assert outcome.failure_note is not None
    assert "write" in outcome.failure_note.read_text(encoding="utf-8")


def test_add_episode_failure_note_includes_the_log_tail(tmp_path):
    from podscribe.cli import add_episode

    config = make_config(tmp_path)
    log = Path(config.paths["log_file"])
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("starting\nboom\n", encoding="utf-8")

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123", config, client=WrongTitleClient(), analyzer=FakeAnalyzer()
    )

    assert outcome.failure_note is not None
    assert "boom" in outcome.failure_note.read_text(encoding="utf-8")


def test_add_episode_dry_run_unmatched_writes_nothing(tmp_path):
    from podscribe.cli import add_episode

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123",
        make_config(tmp_path, macos=True),
        client=WrongTitleClient(),
        analyzer=FakeAnalyzer(),
        dry_run=True,
    )

    assert outcome.status == "unmatched"
    assert outcome.failure_note is not None
    assert outcome.failure_note.name == "_Failed - MCP, CLIs and agents.md"
    assert not outcome.failure_note.exists()
    assert not (tmp_path / "failures").exists()


def test_add_episode_failure_note_write_error_degrades_to_stderr(tmp_path, capsys):
    from podscribe.cli import add_episode

    config = make_config(tmp_path)
    Path(config.paths["failure_notes_dir"]).write_text("not a directory", encoding="utf-8")

    outcome = add_episode(
        "https://open.spotify.com/episode/abc123", config, client=WrongTitleClient(), analyzer=FakeAnalyzer()
    )

    assert outcome.status == "unmatched"
    assert outcome.reason == "unmatched"
    assert outcome.failure_note is None
    assert "could not write failure note" in capsys.readouterr().err

