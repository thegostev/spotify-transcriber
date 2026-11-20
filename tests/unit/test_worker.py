"""Tests for draining the queue through the add pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from podscribe.analyzer import AnalyzerResult
from podscribe.models import EpisodeRef, Segment, Transcript

URL = "https://open.spotify.com/episode/abc123"
FIXED_NOW = datetime(2026, 11, 20, 12, 0, 0)

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
    """Return one fixed transcript and analysis."""

    def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
        transcript = Transcript(
            segments=(Segment(start_seconds=0.0, text="Hello and welcome."),),
            language="en",
            model="Podcast",
            transcribed_at=FIXED_NOW,
        )
        return AnalyzerResult(transcript=transcript, analysis=None, analyzer="command")


def store_for(config):
    from podscribe.queue import open_store

    return open_store(config.paths["data_dir"])


def test_append_log_writes_a_timestamped_line(tmp_path):
    from podscribe.worker import append_log

    path = tmp_path / "logs" / "podscribe.log"
    append_log(path, "hello", now=datetime(2026, 11, 20, 12, 1, 2))

    assert path.read_text(encoding="utf-8") == "[2026-11-20 12:01:02] hello\n"


def test_run_jobs_writes_a_note_and_marks_the_job_done(config_factory):
    from podscribe.queue import enqueue, list_jobs
    from podscribe.worker import run_jobs

    config = config_factory()
    store = store_for(config)
    enqueue(store, URL)
    lines: list[str] = []

    run_jobs(
        config,
        store=store,
        client=FakeClient(),
        analyzer=FakeAnalyzer(),
        log=lines.append,
        once=True,
        now=lambda: FIXED_NOW,
    )

    job = list_jobs(store)[0]
    assert job.state == "done"
    assert job.note_path is not None and Path(job.note_path).exists()
    assert lines[0] == f"start {URL}"
    assert lines[-1] == f"done {URL} -> {job.note_path}"


def test_run_jobs_marks_an_existing_note_done(config_factory):
    from podscribe.queue import enqueue, list_jobs
    from podscribe.worker import run_jobs

    config = config_factory()
    existing = Path(config.paths["output_dir"]) / "26-10-15 MCP, CLIs and agents.md"
    existing.write_text(f'---\nspotify_url: "{URL}"\n---\n\nbody\n', encoding="utf-8")
    store = store_for(config)
    enqueue(store, URL)

    run_jobs(
        config,
        store=store,
        client=FakeClient(),
        analyzer=FakeAnalyzer(),
        log=lambda line: None,
        once=True,
        now=lambda: FIXED_NOW,
    )

    job = list_jobs(store)[0]
    assert job.state == "done"
    assert job.note_path == str(existing)


def run_once(config, store, *, client):
    from podscribe.worker import run_jobs

    lines: list[str] = []
    run_jobs(
        config,
        store=store,
        client=client,
        analyzer=FakeAnalyzer(),
        log=lines.append,
        once=True,
        now=lambda: FIXED_NOW,
    )
    return lines


def test_run_jobs_marks_an_unmatched_episode(config_factory):
    from podscribe.queue import enqueue, list_jobs

    class WrongTitleClient(FakeClient):
        def get_text(self, url: str) -> str:
            text = super().get_text(url)
            if url == URL:
                return text.replace('content="MCP, CLIs and agents"', 'content="Another episode"')
            return text

    config = config_factory()
    store = store_for(config)
    enqueue(store, URL)

    lines = run_once(config, store, client=WrongTitleClient())

    job = list_jobs(store)[0]
    assert job.state == "unmatched"
    assert job.reason == "unmatched episode: Another episode"
    assert lines[-1] == f"unmatched {URL}: Another episode"


def test_run_jobs_marks_a_show_without_a_feed_failed(config_factory):
    from podscribe.queue import enqueue, list_jobs

    class NoFeedClient(FakeClient):
        def get_json(self, url: str):
            return {"results": []}

    config = config_factory()
    store = store_for(config)
    enqueue(store, URL)

    run_once(config, store, client=NoFeedClient())

    job = list_jobs(store)[0]
    assert job.state == "failed"
    assert job.reason == "no public feed for show: Talk Python To Me"


def test_run_jobs_records_an_exception_and_its_traceback(config_factory):
    from podscribe.queue import enqueue, list_jobs
    from podscribe.worker import run_jobs

    class ExplodingAnalyzer(FakeAnalyzer):
        def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
            raise RuntimeError("analyzer boom")

    config = config_factory()
    store = store_for(config)
    enqueue(store, URL)
    lines: list[str] = []

    run_jobs(
        config,
        store=store,
        client=FakeClient(),
        analyzer=ExplodingAnalyzer(),
        log=lines.append,
        once=True,
        now=lambda: FIXED_NOW,
    )

    job = list_jobs(store)[0]
    assert job.state == "failed"
    assert job.reason == "analyzer boom"
    assert lines[0] == f"start {URL}"
    assert f"failed {URL}: analyzer boom" in lines
    assert any("RuntimeError: analyzer boom" in line for line in lines[2:])
