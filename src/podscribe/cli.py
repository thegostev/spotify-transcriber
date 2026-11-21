"""The ``podscribe add`` pipeline: episode link to episode and analysis notes."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from podscribe.analyzer import Analyzer, build_analyzer
from podscribe.config import Config, ConfigError, load_config
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
from podscribe.queue import DONE, QUEUED, RUNNING, Job, enqueue, list_jobs, open_store
from podscribe.remote import RemoteError, load_remote_config, read_status, remote_line, run_subprocess, send_add

SUPERWHISPER_LOCK = Path("~/.superwhisper.lock")
STATUS_TIME_FORMAT = "%H:%M"
TEMP_SUFFIX = ".tmp"


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
        detail: The underlying error message for download, analyzer and write
            failures; None for the other outcomes.
    """

    status: str
    ref: EpisodeRef
    feed_url: str | None = None
    episode_note: Path | None = None
    analysis_note: Path | None = None
    reason: str | None = None
    failure_note: Path | None = None
    detail: str | None = None


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` without ever leaving a partial note.

    The text goes to a temporary file in the same directory and is then
    renamed over ``path``, so a crash or a full disk leaves the old path
    untouched instead of half-written.

    Args:
        path: Destination note.
        text: Complete Markdown document.
    """
    temporary = path.with_name(f".{path.name}{TEMP_SUFFIX}")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


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
    detail: str | None = None,
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
        detail: The underlying error message, when there is one.

    Returns:
        The failure outcome.
    """
    directory = Path(config.paths["failure_notes_dir"])
    note: Path | None = failure_note_path(ref, directory=directory)
    if dry_run:
        return AddOutcome(
            status, ref, feed_url=feed_url, reason=reason, failure_note=note, detail=detail
        )
    try:
        note = write_failure_note(
            ref, reason, directory=directory, occurred_at=occurred_at, log_file=config.paths["log_file"]
        )
    except OSError as exc:
        log_line(f"could not write failure note {note}: {exc}")
        note = None
    if config.notifications.get("macos"):
        notifier(f"podscribe failed: {reason}", f"{ref.show} - {ref.episode_title}")
    return AddOutcome(
        status, ref, feed_url=feed_url, reason=reason, failure_note=note, detail=detail
    )


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
            detail=str(exc),
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
            detail=str(exc),
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
        if analysis_text is not None:
            _write_atomic(analysis_path, analysis_text)
        _write_atomic(episode_path, episode_text)
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
            detail=str(exc),
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
    add = commands.add_parser("add", help="queue one Spotify episode link")
    add.add_argument("episode_url", help="Spotify episode link")
    add.add_argument("--dry-run", action="store_true", help="report what would be queued without writing")
    add.add_argument("--config", default="config.yaml", help="path to config.yaml (default: ./config.yaml)")
    status = commands.add_parser("status", help="list queued, running and finished jobs")
    status.add_argument("--config", default="config.yaml", help="path to config.yaml (default: ./config.yaml)")
    run = commands.add_parser("run", help="process queued links, one at a time")
    run.add_argument("--once", action="store_true", help="drain the queued jobs and exit")
    run.add_argument("--config", default="config.yaml", help="path to config.yaml (default: ./config.yaml)")
    install = commands.add_parser("install-service", help="write the worker LaunchAgent plist")
    install.add_argument("--dry-run", action="store_true", help="print the plist without writing")
    install.add_argument("--config", default="config.yaml", help="path to config.yaml (default: ./config.yaml)")
    remote = commands.add_parser("remote", help="forward add and status to the Mac mini")
    remote_commands = remote.add_subparsers(dest="remote_command", required=True)
    remote_add = remote_commands.add_parser("add", help="queue an episode link on the Mac mini")
    remote_add.add_argument("episode_url", help="Spotify episode link")
    remote_add.add_argument("--dry-run", action="store_true", help="print the far-side command without sending")
    remote_add.add_argument("--config", default="config.yaml", help="laptop config with a remote section")
    remote_status = remote_commands.add_parser("status", help="read the queue on the Mac mini")
    remote_status.add_argument("--config", default="config.yaml", help="laptop config with a remote section")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    client: HttpClientLike | None = None,
    analyzer: Analyzer | None = None,
    remote_run: Callable | None = None,
) -> int:
    """Run the command line; return the process exit code.

    Client and analyzer are built only for commands that need them, so
    ``add`` and ``status`` never load the configured analyzer.

    Args:
        argv: Arguments, ``sys.argv[1:]`` when None.
        client: HTTP client override, used by tests.
        analyzer: Analyzer override, used by tests.
        remote_run: Subprocess runner override for ``remote``, used by tests.

    Returns:
        0 when the command succeeded, 1 otherwise.
    """
    args = build_parser().parse_args(argv)
    if args.command == "remote":
        return _remote_command(args, run=remote_run or run_subprocess)
    config = load_config(args.config)
    if args.command == "add":
        return _add_command(args, config)
    if args.command == "status":
        return _status_command(config)
    if args.command == "run":
        return _run_command(args, config, client=client, analyzer=analyzer)
    if args.command == "install-service":
        return _install_service_command(args, config)
    return 1


def _remote_command(args: argparse.Namespace, *, run: Callable) -> int:
    """Forward ``add`` or ``status`` to the configured transport."""
    try:
        remote = load_remote_config(args.config)
        if args.remote_command == "add":
            if args.dry_run:
                print(f"would run: {remote_line(remote, 'add', args.episode_url)}")
            else:
                send_add(remote, args.episode_url, run=run)
                print(f"sent: {args.episode_url}")
        else:
            for line in read_status(remote, run=run).splitlines():
                print(line)
    except (ConfigError, RemoteError) as exc:
        print(f"podscribe: {exc}", file=sys.stderr)
        return 1
    return 0


def _add_command(args: argparse.Namespace, config: Config) -> int:
    """Queue one episode link and report what happened."""
    if args.dry_run:
        print(f"would queue: {args.episode_url}")
        return 0
    result = enqueue(open_store(config.paths["data_dir"]), args.episode_url)
    if result.status == "already_done":
        print(f"already done: {result.job.note_path or result.job.episode_url}")
    elif result.status in ("already_queued", "already_running"):
        print(f"{result.status.replace('_', ' ')}: {result.job.episode_url}")
    elif result.status == "retry":
        print(f"queued: {result.job.episode_url} (retry)")
    else:
        print(f"queued: {result.job.episode_url}")
    return 0


def _clock(stamp: str | None) -> str:
    """Return the ``HH:MM`` part of an ISO timestamp, ``?`` when unreadable."""
    try:
        return datetime.fromisoformat(stamp or "").strftime(STATUS_TIME_FORMAT)
    except ValueError:
        return "?"


def superwhisper_lock_held(path: Path | str = SUPERWHISPER_LOCK) -> bool:
    """Return True when another process holds the shared Superwhisper lock.

    The probe takes the lock without blocking and releases it at once. A
    missing fcntl module or lock file counts as free, so status stays usable
    without the meeting daemon installed.
    """
    try:
        import fcntl
    except ImportError:
        return False
    try:
        handle = Path(path).expanduser().open("r", encoding="utf-8")
    except OSError:
        return False
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError:
        return False
    finally:
        handle.close()
    return False


def format_status(jobs: list[Job], *, lock_held: Callable[[], bool]) -> list[str]:
    """Render one status line per job, newest first, flagging a held lock."""
    waiting = lock_held() if any(job.state == RUNNING for job in jobs) else False
    lines = []
    for job in jobs:
        if job.state == QUEUED:
            line = f"queued  {job.episode_url}  (added {_clock(job.created_at)})"
        elif job.state == RUNNING:
            line = f"running  {job.episode_url}  (started {_clock(job.started_at)})"
            if waiting:
                line += "  waiting for Superwhisper"
        elif job.state == DONE:
            line = f"done  {job.note_path or job.episode_url}"
        else:
            line = f"{job.state}  {job.episode_url}  ({job.reason or 'no reason'})"
        lines.append(line)
    return lines


def _status_command(config: Config) -> int:
    """Print the queue, newest first, flagging a running job while locked."""
    for line in format_status(list_jobs(open_store(config.paths["data_dir"])), lock_held=superwhisper_lock_held):
        print(line)
    return 0


def _run_command(
    args: argparse.Namespace,
    config: Config,
    *,
    client: HttpClientLike | None,
    analyzer: Analyzer | None,
) -> int:
    """Drain the queue, logging every job to the configured log file."""
    from podscribe.worker import append_log, run_jobs

    http, backend = _dependencies(config, client, analyzer)
    log_file = Path(config.paths["log_file"])
    run_jobs(
        config,
        store=open_store(config.paths["data_dir"]),
        client=http,
        analyzer=backend,
        log=lambda line: append_log(log_file, line),
        once=args.once,
    )
    return 0


def _install_service_command(args: argparse.Namespace, config: Config) -> int:
    """Write or preview the worker plist and print the load command."""
    from podscribe.service import install_service, launch_agent_path, render_plist

    target = launch_agent_path()
    log_file = config.paths["log_file"]
    if args.dry_run:
        print(render_plist(config, config_path=args.config, log_file=log_file), end="")
        print(f"would write: {target}")
    else:
        print(f"wrote: {install_service(config, config_path=args.config, log_file=log_file)}")
    print(f"load with: launchctl bootstrap gui/{os.getuid()} {target}")
    return 0


def _dependencies(
    config: Config, client: HttpClientLike | None, analyzer: Analyzer | None
) -> tuple[HttpClientLike, Analyzer]:
    """Build the HTTP client and analyzer for commands that run the pipeline."""
    http = client or HttpClient(user_agent=str(config.intake["user_agent"]))
    backend = analyzer or build_analyzer(config.analyzer, language=str(config.speech.get("language", "en")))
    return http, backend
