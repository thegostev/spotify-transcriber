"""Drain the queue through the add pipeline, one episode at a time."""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from podscribe.analyzer import Analyzer
from podscribe.cli import add_episode
from podscribe.config import Config
from podscribe.http import HttpClientLike
from podscribe.queue import DONE, FAILED, UNMATCHED, Job, Store, claim_next, finish, requeue_stale

POLL_SECONDS = 60.0
LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
TRACEBACK_TAIL_LINES = 5

Log = Callable[[str], None]
Clock = Callable[[], datetime]


def append_log(log_file: Path | str, line: str, *, now: datetime | None = None) -> None:
    """Append one timestamped line to the log file, creating its directory."""
    path = Path(log_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime(LOG_TIME_FORMAT)
    with path.open("a", encoding="utf-8") as sink:
        sink.write(f"[{stamp}] {line}\n")


def process_job(
    config: Config, job: Job, *, store: Store, client: HttpClientLike,
    analyzer: Analyzer, log: Log, now: datetime,
) -> Job:
    """Run one claimed job through the add pipeline and record the result."""
    log(f"start {job.episode_url}")
    try:
        outcome = add_episode(job.episode_url, config, client=client, analyzer=analyzer, dry_run=False, now=now)
    except Exception as exc:
        log(f"failed {job.episode_url}: {exc}")
        for line in traceback.format_exc().strip().splitlines()[-TRACEBACK_TAIL_LINES:]:
            log(f"  {line}")
        return finish(store, job, FAILED, reason=str(exc), now=now)
    if outcome.status in ("done", "already_done"):
        log(f"done {job.episode_url} -> {outcome.episode_note}")
        return finish(store, job, DONE, note_path=outcome.episode_note, now=now)
    if outcome.status == "unmatched":
        reason = f"unmatched episode: {outcome.ref.episode_title}"
        log(f"unmatched {job.episode_url}: {outcome.ref.episode_title}")
        return finish(store, job, UNMATCHED, reason=reason, now=now)
    if outcome.status == "no_feed":
        reason = f"no public feed for show: {outcome.ref.show}"
    elif outcome.status == "failed":
        reason = outcome.detail or outcome.reason or "add failed"
    else:
        reason = f"add ended as {outcome.status}"
    log(f"failed {job.episode_url}: {reason}")
    return finish(store, job, FAILED, reason=reason, now=now)


def run_jobs(
    config: Config, *, store: Store, client: HttpClientLike, analyzer: Analyzer, log: Log,
    once: bool = False, poll_seconds: float = POLL_SECONDS, now: Clock = datetime.now,
) -> list[Job]:
    """Process queued jobs one at a time; with ``once`` drain the queue first.

    Args:
        config: The validated configuration.
        store: The queue database.
        client: HTTP client passed to the add pipeline.
        analyzer: The configured analyzer.
        log: Sink for one line per event; the CLI wraps it in the log file.
        once: Process the currently queued jobs and return instead of polling.
        poll_seconds: Sleep between empty polls, when not ``once``.
        now: Clock for job timestamps; tests inject a fake.

    Returns:
        The jobs processed in this call, in claim order.
    """
    for stale in requeue_stale(store, now=now()):
        log(f"requeued {stale.episode_url} after a stale run")
    processed: list[Job] = []
    while True:
        job = claim_next(store, now=now())
        if job is None:
            if once:
                return processed
            time.sleep(poll_seconds)
            continue
        processed.append(process_job(config, job, store=store, client=client, analyzer=analyzer, log=log, now=now()))
