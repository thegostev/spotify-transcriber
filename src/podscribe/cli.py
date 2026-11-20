"""The ``podscribe add`` pipeline: episode link to episode and analysis notes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from podscribe.analyzer import Analyzer
from podscribe.config import Config
from podscribe.download import download_audio
from podscribe.episode_page import parse_episode_page
from podscribe.feed import match_feed_item
from podscribe.http import HttpClientLike
from podscribe.itunes import find_feed
from podscribe.models import EpisodeNote, EpisodeRef
from podscribe.note import NoteExistsError, note_names, render_analysis_note, render_episode_note


@dataclass(frozen=True, slots=True)
class AddOutcome:
    """What one ``podscribe add`` run reached.

    Attributes:
        status: planned, done, already_done, no_feed or unmatched.
        ref: The episode link and the metadata read from its page.
        feed_url: The show's feed, when one was found.
        episode_note: Target or written episode note, None when there is none.
        analysis_note: Target or written analysis note, None when there is none.
    """

    status: str
    ref: EpisodeRef
    feed_url: str | None = None
    episode_note: Path | None = None
    analysis_note: Path | None = None


def add_episode(
    episode_url: str,
    config: Config,
    *,
    client: HttpClientLike,
    analyzer: Analyzer,
    dry_run: bool = False,
    now: datetime | None = None,
) -> AddOutcome:
    """Resolve one episode link and write its notes.

    A dry run stops after the feed match and returns the target paths.

    Args:
        episode_url: Spotify episode link the user sent.
        config: Validated configuration; paths, intake and analyzer sections.
        client: HTTP client for the page, search, feed and audio.
        analyzer: The configured analyzer.
        dry_run: Resolve and report without downloading or writing.
        now: Time written as ``analyzed_at``; defaults to the current time.

    Returns:
        The outcome, with the note paths that were planned or written.
    """
    ref = parse_episode_page(client.get_text(episode_url))
    feed_url = find_feed(ref.show, client, search_url=config.intake["itunes_search_url"])
    if feed_url is None:
        return AddOutcome("no_feed", ref)
    item = match_feed_item(
        client.get_text(feed_url), ref, tolerance_days=int(config.intake["match_window_days"])
    )
    if item is None:
        return AddOutcome("unmatched", ref, feed_url=feed_url)
    output_dir = Path(config.paths["output_dir"])
    try:
        names = note_names(ref, ref.show, output_dir=output_dir)
    except NoteExistsError as exc:
        return AddOutcome("already_done", ref, feed_url=feed_url, episode_note=exc.path)
    episode_path = output_dir / names.episode
    analysis_path = output_dir / names.analysis
    if dry_run:
        return AddOutcome("planned", ref, feed_url=feed_url, episode_note=episode_path, analysis_note=analysis_path)
    audio = download_audio(item, Path(config.paths["data_dir"]) / "audio", client)
    result = analyzer.analyze(audio, ref)
    has_analysis = bool(result.analysis)
    note = EpisodeNote(
        ref=ref,
        feed_url=feed_url,
        transcript=result.transcript,
        duration_seconds=item.duration_seconds,
        cleanup="skipped",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    episode_text = render_episode_note(
        note, analysis_note=names.analysis if has_analysis else None, analyzer=result.analyzer
    )
    episode_path.write_text(episode_text, encoding="utf-8")
    if not result.analysis:
        return AddOutcome("done", ref, feed_url=feed_url, episode_note=episode_path)
    analysis_path.write_text(
        render_analysis_note(
            ref=ref,
            analyzer=result.analyzer,
            analysis=result.analysis,
            analyzed_at=now or datetime.now(),
            episode_note=names.episode,
        ),
        encoding="utf-8",
    )
    return AddOutcome(
        "done", ref, feed_url=feed_url, episode_note=episode_path, analysis_note=analysis_path
    )
