"""Tests for the analyzer seam: shared result types and backend adapters."""

from pathlib import Path

import pytest

from podscribe.models import EpisodeRef, Segment, Transcript

REF = EpisodeRef(spotify_url="https://open.spotify.com/episode/abc", show="Show", episode_title="Episode")


@pytest.mark.xfail(strict=True, reason="LAG-1058")
def test_analyzer_result_carries_transcript_analysis_and_backend():
    from podscribe.analyzer import AnalyzerResult

    transcript = Transcript(segments=(Segment(0.0, "Hello."),), language="en", model="fake")
    result = AnalyzerResult(transcript=transcript, analysis="Notes", analyzer="fake")

    assert result.transcript == transcript
    assert result.analysis == "Notes"
    assert result.analyzer == "fake"


@pytest.mark.xfail(strict=True, reason="LAG-1058")
def test_analyzer_protocol_accepts_a_structural_implementation():
    from podscribe.analyzer import Analyzer, AnalyzerResult

    class FakeAnalyzer:
        def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
            transcript = Transcript(segments=(Segment(0.0, ref.episode_title),), language="en", model="fake")
            return AnalyzerResult(transcript=transcript, analysis=None, analyzer="fake")

    analyzer: Analyzer = FakeAnalyzer()
    result = analyzer.analyze(Path("episode.mp3"), REF)

    assert result.transcript.segments[0].text == "Episode"


@pytest.mark.xfail(strict=True, reason="LAG-1058")
def test_single_segment_helper_puts_text_at_zero():
    from podscribe.analyzer import single_segment

    assert single_segment(" a b ") == (Segment(0.0, "a b"),)
