"""The analyzer seam: one config-selected component turns audio into text.

Backends implement :class:`Analyzer`; the pipeline depends only on the types
here, never on a backend's own result objects.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from podscribe.config import ConfigError
from podscribe.models import EpisodeRef, Segment, Transcript

DEFAULT_TIMEOUT_SECONDS = 3600.0
BUCKET_SECONDS = 30.0
MIN_BUCKET_SECONDS = 20.0
SENTENCE_ENDINGS = (".", "!", "?")


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
    word_level = bool(raw) and all(isinstance(item, dict) and "end" in item for item in raw)
    if word_level:
        return bucket_words(raw)
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


def _normalise_module_result(raw: object, name: str, language: str) -> AnalyzerResult:
    """Turn a module backend's return value into an AnalyzerResult."""
    if isinstance(raw, AnalyzerResult):
        return AnalyzerResult(transcript=raw.transcript, analysis=raw.analysis, analyzer=f"module:{name}")
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        text, analysis = raw
        if isinstance(text, str) and text.strip():
            analysis_text = analysis.strip() if isinstance(analysis, str) and analysis.strip() else None
            transcript = Transcript(segments=single_segment(text), language=language, model=name)
            return AnalyzerResult(transcript=transcript, analysis=analysis_text, analyzer=f"module:{name}")
    raise AnalyzerError(f"analyzer module {name} returned neither AnalyzerResult nor (text, analysis)")


@dataclass(frozen=True, slots=True)
class ModuleAnalyzer:
    """Load ``package.module:Class`` and call its ``analyze(audio, ref)``.

    Attributes:
        path: Import path with a class name, e.g. ``my_package.mod:Analyzer``.
        language: Language code used when the module returns a bare text pair.
    """

    path: str
    language: str = "en"

    def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
        """Load the configured class and normalise whatever it returns.

        Raises:
            AnalyzerError: The path is invalid, import fails or the result
                is neither an AnalyzerResult nor a (text, analysis) pair.
        """
        module_name, _, class_name = self.path.partition(":")
        if not module_name or not class_name:
            raise AnalyzerError(f"analyzer module path must be package.module:Class, got {self.path!r}")
        try:
            backend = getattr(importlib.import_module(module_name), class_name)()
            raw = backend.analyze(audio, ref)
        except AnalyzerError:
            raise
        except Exception as exc:
            raise AnalyzerError(f"analyzer module {self.path} failed: {exc}") from exc
        return _normalise_module_result(raw, module_name, self.language)


def _load_superwhisper_client(wf_path: Path):
    """Import lane B's ``superwhisper_client`` from the configured workflow path."""
    module = sys.modules.get("superwhisper_client")
    if module is not None:
        return module
    location = str(Path(wf_path).expanduser())
    if location not in sys.path:
        sys.path.insert(0, location)
    try:
        return importlib.import_module("superwhisper_client")
    except ImportError as exc:
        raise AnalyzerError(f"cannot import superwhisper_client from {location}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class SuperwhisperAnalyzer:
    """Call SuperwhisperObsidianWF's ``analyze_file`` for one audio file.

    Attributes:
        wf_path: The workflow checkout that carries ``superwhisper_client``.
        mode_key: Superwhisper Custom Mode key, e.g. ``podcast``.
        timeout_seconds: Wall-clock limit while Superwhisper runs.
        language: Language code when the workflow reports none.
    """

    wf_path: Path
    mode_key: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    language: str = "en"

    def analyze(self, audio: Path, ref: EpisodeRef) -> AnalyzerResult:
        """Run one Superwhisper pass and map its result onto the note types.

        The Podcast mode is a cleanup prompt, so any non-empty analysis is
        accepted: ``contract_check=None``.

        Raises:
            AnalyzerError: The client cannot be imported, the run fails or
                it returns no transcript.
        """
        client = _load_superwhisper_client(self.wf_path)
        try:
            raw = client.analyze_file(
                str(audio), mode_key=self.mode_key, timeout=self.timeout_seconds, contract_check=None
            )
        except Exception as exc:
            raise AnalyzerError(f"superwhisper analyzer failed: {exc}") from exc
        text = getattr(raw, "transcript", None)
        if not isinstance(text, str) or not text.strip():
            raise AnalyzerError("superwhisper analyzer returned no transcript")
        words = getattr(raw, "segments", ()) or ()
        segments = bucket_words(words) if words else single_segment(text)
        analysis = getattr(raw, "analysis", None)
        analysis_text = analysis.strip() if isinstance(analysis, str) and analysis.strip() else None
        model = getattr(raw, "mode_name", None) or "superwhisper"
        transcript = Transcript(segments=segments or single_segment(text), language=self.language, model=str(model))
        return AnalyzerResult(transcript=transcript, analysis=analysis_text, analyzer="superwhisper")


def build_analyzer(section: Mapping[str, Any], *, language: str = "en") -> Analyzer:
    """Build the backend selected by ``analyzer.backend``.

    Args:
        section: The validated ``analyzer`` config section.
        language: Language code for backends that do not report one.

    Raises:
        ConfigError: The backend is unknown or its settings are missing.
    """
    backend = section.get("backend")
    options = section.get(backend) if isinstance(backend, str) else None
    if not isinstance(options, Mapping):
        raise ConfigError(f"analyzer backend {backend!r} has no settings section")
    if backend == "command":
        argv = options.get("argv")
        if not isinstance(argv, list) or not argv:
            raise ConfigError("analyzer.command.argv must be a non-empty list")
        timeout = float(options.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
        return CommandAnalyzer(argv=tuple(str(part) for part in argv), timeout_seconds=timeout, language=language)
    if backend == "module":
        path = options.get("path")
        if not isinstance(path, str) or not path:
            raise ConfigError("analyzer.module.path must be package.module:Class")
        return ModuleAnalyzer(path=path, language=language)
    if backend == "superwhisper":
        wf_path, mode_key = options.get("wf_path"), options.get("mode_key")
        if not isinstance(wf_path, str) or not wf_path or not isinstance(mode_key, str) or not mode_key:
            raise ConfigError("analyzer.superwhisper needs wf_path and mode_key")
        timeout = float(options.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
        return SuperwhisperAnalyzer(
            wf_path=Path(wf_path).expanduser(), mode_key=mode_key, timeout_seconds=timeout, language=language
        )
    raise ConfigError(f"unknown analyzer backend {backend!r}; expected command, module or superwhisper")


def _piece(piece: object) -> tuple[float, float, str]:
    """Read start, end and text from a word object or a mapping."""
    if isinstance(piece, Mapping):
        start, end, text = piece.get("start", 0.0), piece.get("end"), piece.get("text", "")
    else:
        start, end, text = getattr(piece, "start", 0.0), getattr(piece, "end", None), getattr(piece, "text", "")
    return float(start), float(end) if isinstance(end, (int, float)) else float(start), str(text)


def bucket_words(pieces: Iterable[object]) -> tuple[Segment, ...]:
    """Group word-level timestamps into readable lines of about 20-40 seconds.

    A line closes at a sentence end once it is 20 s old, or at 30 s otherwise.

    Args:
        pieces: Word-level items with ``start``, ``end`` and ``text``, as
            mappings or attribute objects.

    Returns:
        One segment per line, in playback order; empty when no word has text.
    """
    segments: list[Segment] = []
    words: list[str] = []
    start: float | None = None
    end = 0.0
    for piece in pieces:
        piece_start, piece_end, text = _piece(piece)
        text = text.strip()
        if not text:
            continue
        if start is None:
            start = piece_start
        words.append(text)
        end = max(piece_end, piece_start)
        elapsed = end - start
        if elapsed >= BUCKET_SECONDS or (elapsed >= MIN_BUCKET_SECONDS and text.endswith(SENTENCE_ENDINGS)):
            segments.append(Segment(start_seconds=start, text=" ".join(words)))
            words, start = [], None
    if words and start is not None:
        segments.append(Segment(start_seconds=start, text=" ".join(words)))
    return tuple(segments)
