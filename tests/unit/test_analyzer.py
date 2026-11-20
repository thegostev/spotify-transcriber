"""Tests for the analyzer seam: shared result types and backend adapters."""

import sys
from pathlib import Path

import pytest

from podscribe.models import EpisodeRef, Segment, Transcript

REF = EpisodeRef(spotify_url="https://open.spotify.com/episode/abc", show="Show", episode_title="Episode")


def test_analyzer_result_carries_transcript_analysis_and_backend():
    from podscribe.analyzer import AnalyzerResult

    transcript = Transcript(segments=(Segment(0.0, "Hello."),), language="en", model="fake")
    result = AnalyzerResult(transcript=transcript, analysis="Notes", analyzer="fake")

    assert result.transcript == transcript
    assert result.analysis == "Notes"
    assert result.analyzer == "fake"


def test_analyzer_protocol_accepts_a_structural_implementation():
    from podscribe.analyzer import Analyzer, AnalyzerResult

    class FakeAnalyzer:
        def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
            transcript = Transcript(segments=(Segment(0.0, ref.episode_title),), language="en", model="fake")
            return AnalyzerResult(transcript=transcript, analysis=None, analyzer="fake")

    analyzer: Analyzer = FakeAnalyzer()
    result = analyzer.analyze(Path("episode.mp3"), REF)

    assert result.transcript.segments[0].text == "Episode"


def test_single_segment_helper_puts_text_at_zero():
    from podscribe.analyzer import single_segment

    assert single_segment(" a b ") == (Segment(0.0, "a b"),)


def _command(tmp_path: Path, body: str, *, timeout: float = 30.0):
    from podscribe.analyzer import CommandAnalyzer

    script = tmp_path / "backend.py"
    script.write_text(body, encoding="utf-8")
    return CommandAnalyzer(argv=(sys.executable, str(script), "{audio}"), timeout_seconds=timeout)


def test_command_analyzer_maps_json_to_one_segment_and_analysis(tmp_path):
    audio = tmp_path / "episode.mp3"
    audio.write_bytes(b"audio")
    analyzer = _command(
        tmp_path,
        "import json, sys\n"
        "assert sys.argv[1].endswith('episode.mp3')\n"
        "print(json.dumps({'transcript': ' Hello world. ', 'analysis': ' Notes '}))\n",
    )

    result = analyzer.analyze(audio, REF)

    assert result.analyzer == "command"
    assert result.transcript == Transcript(
        segments=(Segment(0.0, "Hello world."),), language="en", model="command"
    )
    assert result.analysis == "Notes"


def test_command_analyzer_uses_optional_segments_and_drops_empty_analysis(tmp_path):
    analyzer = _command(
        tmp_path,
        "import json\n"
        "print(json.dumps({'transcript': 'ignored', 'analysis': '', 'segments': ["
        "{'start': 0, 'text': 'First'}, {'start': 12.5, 'text': ' Second '}]}))\n",
    )

    result = analyzer.analyze(tmp_path / "episode.mp3", REF)

    assert result.transcript.segments == (Segment(0.0, "First"), Segment(12.5, "Second"))
    assert result.analysis is None


@pytest.mark.parametrize(
    "body",
    [
        "import sys; sys.exit(2)",
        "print('not json')",
        "print('[1, 2]')",
        "import json; print(json.dumps({'analysis': 'no transcript'}))",
        "import json; print(json.dumps({'transcript': 'x', 'segments': 'nope'}))",
    ],
)
def test_command_analyzer_rejects_bad_output(tmp_path, body):
    from podscribe.analyzer import AnalyzerError

    with pytest.raises(AnalyzerError):
        _command(tmp_path, body).analyze(tmp_path / "episode.mp3", REF)


def test_command_analyzer_times_out(tmp_path):
    from podscribe.analyzer import AnalyzerError

    analyzer = _command(tmp_path, "import time; time.sleep(5)\n", timeout=0.1)

    with pytest.raises(AnalyzerError, match="timed out|failed"):
        analyzer.analyze(tmp_path / "episode.mp3", REF)
