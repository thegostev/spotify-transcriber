"""The ``podscribe add`` pipeline: episode link to episode and analysis notes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from podscribe.analyzer import Analyzer, build_analyzer
from podscribe.config import Config, load_config
from podscribe.download import download_audio
from podscribe.episode_page import parse_episode_page
from podscribe.failure import (
    Notifier,
    clear_failure_note,
    failure_note_path,
    log_line,
    notify_macos,
    write_failure_note,
)
from podscribe.feed import match_feed_item
from podscribe.http import HttpClient, HttpClientLike
from podscribe.itunes import find_feed
from podscribe.models import EpisodeNote, EpisodeRef
from podscribe.note import NoteExistsError, note_names, render_analysis_note, render_episode_note

SUCCESS_STATUSES = ("planned", "done")


@dataclass(frozen=True, slots=True)
class AddOutcome:
    """What one ``podscribe add`` run reached.

    Attributes:
        status: planned, done, already_done, no_feed, unmatched or failed.
        ref: The episode link and the metadata read from its page.
        feed_url: The show's feed, when one was found.
        episode_note: Target or written episode note, None when there is none.
        analysis_note: Target or written analysis note, None when there is none.
        reason: unmatched, download, analyzer or write; None on success.
        failure_note: Written or would-be failure note, None when none was made.
    """

    status: str
    ref: EpisodeRef
    feed_url: str | None = None
    episode_note: Path | None = None
    analysis_note: Path | None = None
    reason: str | None = None
    failure_note: Path | None = None


def _record_failure(
    status: str,
    reason: str,
    *,
    ref: EpisodeRef,
    feed_url: str | None,
    config: Config,
    occurred_at: datetime,
    dry_run: bool,
    notifier: Notifier,
) -> AddOutcome:
    """Write the failure note, or report its path during a dry run.

    A failure note that cannot be written must not raise: the run is already
    failing, so the note path degrades to None and stderr carries the reason.

    Args:
        status: no_feed, unmatched or failed; kept for the caller's output.
        reason: unmatched, download, analyzer or write.
        ref: The episode link and its metadata.
        feed_url: The show's feed, when one was found.
        config: Validated configuration; paths only.
        occurred_at: When the failure was recorded.
        dry_run: Report the would-be path without writing anything.
        notifier: Called once when ``notifications.macos`` is true.

    Returns:
        The failure outcome.
    """
    directory = Path(config.paths["failure_notes_dir"])
    note: Path | None = failure_note_path(ref, directory=directory)
    if dry_run:
        return AddOutcome(status, ref, feed_url=feed_url, reason=reason, failure_note=note)
    try:
        note = write_failure_note(
            ref, reason, directory=directory, occurred_at=occurred_at, log_file=config.paths["log_file"]
        )
    except OSError as exc:
        log_line(f"could not write failure note {note}: {exc}")
        note = None
    if config.notifications.get("macos"):
        notifier(f"podscribe failed: {reason}", f"{ref.show} - {ref.episode_title}")
    return AddOutcome(status, ref, feed_url=feed_url, reason=reason, failure_note=note)


def add_episode(
    episode_url: str,
    config: Config,
    *,
    client: HttpClientLike,
    analyzer: Analyzer,
    dry_run: bool = False,
    now: datetime | None = None,
    notifier: Notifier | None = None,
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
        notifier: Failure notifier; ``osascript`` when None.

    Returns:
        The outcome, with the note paths that were planned or written.
    """
    notify = notifier or notify_macos
    ref = parse_episode_page(client.get_text(episode_url))
    feed_url = find_feed(ref.show, client, search_url=config.intake["itunes_search_url"])
    if feed_url is None:
        return _record_failure(
            "no_feed",
            "unmatched",
            ref=ref,
            feed_url=None,
            config=config,
            occurred_at=now or datetime.now(),
            dry_run=dry_run,
            notifier=notify,
        )
    item = match_feed_item(
        client.get_text(feed_url), ref, tolerance_days=int(config.intake["match_window_days"])
    )
    if item is None:
        return _record_failure(
            "unmatched",
            "unmatched",
            ref=ref,
            feed_url=feed_url,
            config=config,
            occurred_at=now or datetime.now(),
            dry_run=dry_run,
            notifier=notify,
        )
    output_dir = Path(config.paths["output_dir"])
    try:
        names = note_names(ref, ref.show, output_dir=output_dir)
    except NoteExistsError as exc:
        if not dry_run:
            clear_failure_note(ref, directory=Path(config.paths["failure_notes_dir"]))
        return AddOutcome("already_done", ref, feed_url=feed_url, episode_note=exc.path)
    episode_path = output_dir / names.episode
    analysis_path = output_dir / names.analysis
    if dry_run:
        return AddOutcome("planned", ref, feed_url=feed_url, episode_note=episode_path, analysis_note=analysis_path)
    try:
        audio = download_audio(item, Path(config.paths["data_dir"]) / "audio", client)
    except OSError as exc:
        log_line(f"download failed for {ref.episode_title}: {exc}")
        return _record_failure(
            "failed",
            "download",
            ref=ref,
            feed_url=feed_url,
            config=config,
            occurred_at=now or datetime.now(),
            dry_run=dry_run,
            notifier=notify,
        )
    try:
        result = analyzer.analyze(audio, ref)
    except Exception as exc:
        log_line(f"analyzer failed for {ref.episode_title}: {exc}")
        return _record_failure(
            "failed",
            "analyzer",
            ref=ref,
            feed_url=feed_url,
            config=config,
            occurred_at=now or datetime.now(),
            dry_run=dry_run,
            notifier=notify,
        )
    has_analysis = bool(result.analysis)
    stamp = now or datetime.now()
    transcript = result.transcript
    if transcript.transcribed_at is None:
        transcript = replace(transcript, transcribed_at=stamp)
    note = EpisodeNote(
        ref=ref,
        feed_url=feed_url,
        transcript=transcript,
        duration_seconds=item.duration_seconds,
        cleanup="skipped",
    )
    episode_text = render_episode_note(
        note, analysis_note=names.analysis if has_analysis else None, analyzer=result.analyzer
    )
    analysis_text = None
    if result.analysis:
        analysis_text = render_analysis_note(
            ref=ref,
            analyzer=result.analyzer,
            analysis=result.analysis,
            analyzed_at=stamp,
            episode_note=names.episode,
        )
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        episode_path.write_text(episode_text, encoding="utf-8")
        if analysis_text is not None:
            analysis_path.write_text(analysis_text, encoding="utf-8")
    except OSError as exc:
        log_line(f"could not write notes for {ref.episode_title}: {exc}")
        return _record_failure(
            "failed",
            "write",
            ref=ref,
            feed_url=feed_url,
            config=config,
            occurred_at=now or datetime.now(),
            dry_run=dry_run,
            notifier=notify,
        )
    clear_failure_note(ref, directory=Path(config.paths["failure_notes_dir"]))
    return AddOutcome(
        "done",
        ref,
        feed_url=feed_url,
        episode_note=episode_path,
        analysis_note=analysis_path if analysis_text is not None else None,
    )


def build_parser() -> argparse.ArgumentParser:
    """Return the command line parser for ``podscribe``."""
    parser = argparse.ArgumentParser(prog="podscribe", description="Turn podcast episodes into Obsidian notes.")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="write notes for one Spotify episode link")
    add.add_argument("episode_url", help="Spotify episode link")
    add.add_argument("--dry-run", action="store_true", help="resolve the feed match without downloading or writing")
    add.add_argument("--config", default="config.yaml", help="path to config.yaml (default: ./config.yaml)")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    client: HttpClientLike | None = None,
    analyzer: Analyzer | None = None,
) -> int:
    """Run the command line; return the process exit code.

    Args:
        argv: Arguments, ``sys.argv[1:]`` when None.
        client: HTTP client override, used by tests.
        analyzer: Analyzer override, used by tests.

    Returns:
        0 when the episode was planned or written, 1 otherwise.
    """
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    http = client or HttpClient(user_agent=str(config.intake["user_agent"]))
    backend = analyzer or build_analyzer(config.analyzer, language=str(config.speech.get("language", "en")))
    outcome = add_episode(args.episode_url, config, client=http, analyzer=backend, dry_run=args.dry_run)
    if outcome.status == "planned":
        print(f"would write: {outcome.episode_note}")
        print(f"would write: {outcome.analysis_note}")
    elif outcome.status == "done":
        print(f"wrote: {outcome.episode_note}")
        if outcome.analysis_note:
            print(f"wrote: {outcome.analysis_note}")
        else:
            print("no analysis")
    elif outcome.status == "already_done":
        print(f"already done: {outcome.episode_note}")
    elif outcome.status == "no_feed":
        print(f"no public feed for show: {outcome.ref.show}")
    elif outcome.status == "unmatched":
        print(f"unmatched episode: {outcome.ref.episode_title}")
    else:
        print(f"episode failed: {outcome.ref.episode_title}")
    if outcome.reason:
        print(f"failure reason: {outcome.reason}")
    if outcome.failure_note:
        print(f"failure note: {outcome.failure_note}")
    return 0 if outcome.status in SUCCESS_STATUSES else 1
