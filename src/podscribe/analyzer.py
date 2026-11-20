"""The analyzer seam: one config-selected component turns audio into text.

Backends implement :class:`Analyzer`; the pipeline depends only on the types
here, never on a backend's own result objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from podscribe.models import EpisodeRef, Segment, Transcript


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
