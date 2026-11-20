"""The analyzer seam: one config-selected component turns audio into text.

Backends implement :class:`Analyzer`; the pipeline depends only on the types
here, never on a backend's own result objects.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from podscribe.models import EpisodeRef, Segment, Transcript

DEFAULT_TIMEOUT_SECONDS = 3600.0


class AnalyzerError(Exception):
    """The configured analyzer failed to produce a usable result."""


@dataclass(frozen=True, slots=True)
class AnalyzerResult:
    """What one analyzer run yields.

    Attributes:
        transcript: Time-stamped speech; one segment when the backend has none.
        analysis: The analyzer's Markdown, None when the backend gives none.
        analyzer: Backend name for the note: superwhisper, command or module:<name>.
    """

    transcript: Transcript
    analysis: str | None
    analyzer: str


class Analyzer(Protocol):
    """The one pluggable component between downloaded audio and the note."""

    def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
        """Turn ``audio`` for ``ref`` into a transcript and optional analysis."""


def single_segment(text: str) -> tuple[Segment, ...]:
    """Return a one-segment transcript for a backend that gives no timestamps."""
    return (Segment(start_seconds=0.0, text=text.strip()),)


def _segment_list(raw: object) -> tuple[Segment, ...]:
    """Validate a command backend's optional ``segments`` list."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise AnalyzerError("analyzer command: segments must be a list")
    segments = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise AnalyzerError("analyzer command: each segment needs a text string")
        try:
            start = float(item.get("start", 0.0))
        except (TypeError, ValueError) as exc:
            raise AnalyzerError("analyzer command: segment start must be a number") from exc
        if item["text"].strip():
            segments.append(Segment(start_seconds=start, text=item["text"].strip()))
    return tuple(segments)


@dataclass(frozen=True, slots=True)
class CommandAnalyzer:
    """Run any executable that prints the analyzer JSON contract on stdout.

    Attributes:
        argv: Command and arguments; ``{audio}`` in any part is replaced.
        timeout_seconds: Wall-clock limit for one run.
        language: Language code written to the transcript.
    """

    argv: tuple[str, ...]
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    language: str = "en"

    def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
        """Run the command for ``audio`` and parse its stdout.

        Raises:
            AnalyzerError: Non-zero exit, timeout, bad JSON or no transcript.
        """
        argv = [part.replace("{audio}", str(audio)) for part in self.argv]
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout_seconds)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AnalyzerError(f"analyzer command failed to run: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"exit {completed.returncode}"
            raise AnalyzerError(f"analyzer command failed: {detail}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AnalyzerError("analyzer command: stdout is not JSON") from exc
        if not isinstance(payload, dict):
            raise AnalyzerError("analyzer command: stdout JSON must be an object")
        text = payload.get("transcript")
        if not isinstance(text, str) or not text.strip():
            raise AnalyzerError("analyzer command: output has no transcript")
        segments = _segment_list(payload.get("segments")) or single_segment(text)
        analysis = payload.get("analysis")
        analysis_text = analysis.strip() if isinstance(analysis, str) and analysis.strip() else None
        transcript = Transcript(segments=segments, language=self.language, model="command")
        return AnalyzerResult(transcript=transcript, analysis=analysis_text, analyzer="command")
