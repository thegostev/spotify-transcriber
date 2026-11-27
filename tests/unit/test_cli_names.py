"""The analysis note gets canonical guest, host and brand names (LAG-1071)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

TITLE = "Navigating Cloud Infrastructure using AI with Marcin Wyszynski, Spacelift"
ANALYSIS = """---
title: "Cloud infrastructure"
guest: "Marcin Grzemski"
host: "unknown"
topics: [terraform]
---

## Who is talking

- **Guest:** Marcin Grzemski, cofounder of SpaceLift.
- **Host:** unknown.
"""

SPOTIFY_HTML = f"""
<html><head>
  <meta property="og:title" content="{TITLE}">
  <meta property="og:description" content="Software Architecture Insights · Episode">
  <meta property="og:url" content="https://open.spotify.com/episode/sai1">
  <meta name="music:release_date" content="2026-01-13T00:00:00Z">
</head></html>
"""

ITUNES_JSON = {
    "results": [
        {
            "collectionName": "Software Architecture Insights",
            "trackName": "Software Architecture Insights",
            "feedUrl": "https://feeds.example/sai",
        }
    ]
}

FEED_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Software Architecture Insights</title>
    <itunes:author>Lee Atchison</itunes:author>
    <item>
      <title>{TITLE}</title>
      <pubDate>Tue, 13 Jan 2026 09:00:00 GMT</pubDate>
      <itunes:duration>00:31:00</itunes:duration>
      <enclosure url="https://cdn.example/sai1.mp3" type="audio/mpeg" length="1"/>
    </item>
  </channel>
</rss>
"""


class FakeClient:
    """Serve the three intake responses and write a stand-in audio file."""

    def get_text(self, url: str) -> str:
        if url == "https://open.spotify.com/episode/sai1":
            return SPOTIFY_HTML
        if url == "https://feeds.example/sai":
            return FEED_XML
        raise AssertionError(f"unexpected URL {url}")

    def get_json(self, url: str):
        assert url.startswith("https://itunes.example/search")
        return ITUNES_JSON

    def download(self, url: str, destination: Path) -> Path:
        destination.write_bytes(b"ID3 fake audio")
        return destination


class FakeAnalyzer:
    """Return an analysis that repeats the speech engine's name spellings."""

    def analyze(self, audio: Path, ref):
        from podscribe.analyzer import AnalyzerResult
        from podscribe.models import Segment, Transcript

        transcript = Transcript(
            segments=(Segment(start_seconds=0.0, text="Hello."),),
            language="en",
            model="Podcast",
            transcribed_at=datetime(2026, 11, 21, 16, 0, 0),
        )
        return AnalyzerResult(transcript=transcript, analysis=ANALYSIS, analyzer="superwhisper")


def make_config(tmp_path: Path, *, names: dict | None = None):
    from podscribe.config import Config

    output_dir = tmp_path / "out"
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
        analyzer={"backend": "command", "command": {"argv": ["fake", "{audio}"]}},
        speech={},
        llm={},
        notifications={"macos": False},
        remote={"transport": "rex", "rex_host": "mini", "rex_session": "p", "ssh_target": "h@m"},
        analysis={"names": names or {}},
        source=tmp_path / "config.yaml",
    )


def written_analysis(tmp_path: Path) -> str:
    (note,) = (tmp_path / "out").glob("*- Analysis.md")
    return note.read_text(encoding="utf-8")


def test_add_episode_writes_the_canonical_guest_and_host(tmp_path):
    from podscribe.cli import add_episode

    outcome = add_episode(
        "https://open.spotify.com/episode/sai1", make_config(tmp_path), client=FakeClient(), analyzer=FakeAnalyzer()
    )

    text = written_analysis(tmp_path)
    assert outcome.status == "done"
    assert 'guest: "Marcin Wyszynski"' in text
    assert 'host: "Lee Atchison"' in text
    assert "SpaceLift" not in text


def test_add_episode_applies_the_configured_alias_to_the_body(tmp_path):
    from podscribe.cli import add_episode

    config = make_config(tmp_path, names={"aliases": {"Grzemski": "Wyszynski"}})
    add_episode("https://open.spotify.com/episode/sai1", config, client=FakeClient(), analyzer=FakeAnalyzer())

    text = written_analysis(tmp_path)

    assert "Grzemski" not in text
    assert 'guest: "Marcin Wyszynski"' in text
