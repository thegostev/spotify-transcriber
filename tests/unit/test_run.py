"""Tests for the run and install-service commands."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from podscribe.analyzer import AnalyzerResult
from podscribe.models import EpisodeRef, Segment, Transcript

URL = "https://open.spotify.com/episode/abc123"

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

    def get_text(self, url: str) -> str:
        if url == URL:
            return SPOTIFY_HTML
        if url == "https://feeds.example/talkpython":
            return FEED_XML
        raise AssertionError(f"unexpected URL {url}")

    def get_json(self, url: str):
        return ITUNES_JSON

    def download(self, url: str, destination: Path) -> Path:
        destination.write_bytes(b"ID3 fake audio")
        return destination


class FakeAnalyzer:
    """Return one fixed transcript."""

    def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
        transcript = Transcript(
            segments=(Segment(start_seconds=0.0, text="Hello and welcome."),),
            language="en",
            model="Podcast",
            transcribed_at=datetime(2026, 11, 20, 12, 0, 0),
        )
        return AnalyzerResult(transcript=transcript, analysis=None, analyzer="command")


def test_main_run_once_drains_the_queue_and_logs(config_factory, monkeypatch):
    import podscribe.cli as cli
    from podscribe.queue import enqueue, list_jobs, open_store

    config = config_factory()
    enqueue(open_store(config.paths["data_dir"]), URL)
    monkeypatch.setattr(cli, "load_config", lambda path: config)

    exit_code = cli.main(["run", "--once"], client=FakeClient(), analyzer=FakeAnalyzer())

    assert exit_code == 0
    job = list_jobs(open_store(config.paths["data_dir"]))[0]
    assert job.state == "done"
    assert job.note_path is not None and Path(job.note_path).exists()
    log = Path(config.paths["log_file"]).read_text(encoding="utf-8")
    assert f"] start {URL}\n" in log
    assert f"] done {URL} -> {job.note_path}\n" in log


def test_main_install_service_dry_run_prints_the_plist(tmp_path, config_factory, capsys, monkeypatch):
    import podscribe.cli as cli

    config = config_factory()
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    target = tmp_path / "home" / "Library" / "LaunchAgents" / "com.podscribe.worker.plist"

    exit_code = cli.main(["install-service", "--dry-run", "--config", str(tmp_path / "config.yaml")])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "<key>Label</key>" in out
    assert "com.podscribe.worker" in out
    assert f"would write: {target}" in out
    assert "launchctl bootstrap gui/" in out
    assert not target.exists()


def test_main_install_service_writes_the_plist_and_prints_the_load_command(
    tmp_path, config_factory, capsys, monkeypatch
):
    import podscribe.cli as cli

    config = config_factory()
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    target = tmp_path / "home" / "Library" / "LaunchAgents" / "com.podscribe.worker.plist"

    exit_code = cli.main(["install-service", "--config", str(tmp_path / "config.yaml")])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert target.exists()
    assert f"wrote: {target}" in out
    assert "launchctl bootstrap gui/" in out and str(target) in out
