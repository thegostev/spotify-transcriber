"""Drain the queue through the add pipeline, one episode at a time."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from podscribe.analyzer import Analyzer
from podscribe.cli import add_episode
from podscribe.config import Config
from podscribe.http import HttpClientLike
from podscribe.queue import DONE, FAILED, Job, Store, claim_next, finish

POLL_SECONDS = 60.0
LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

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
    outcome = add_episode(job.episode_url, config, client=client, analyzer=analyzer, dry_run=False, now=now)
    if outcome.status in ("done", "already_done"):
        log(f"done {job.episode_url} -> {outcome.episode_note}")
        return finish(store, job, DONE, note_path=outcome.episode_note, now=now)
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
    processed: list[Job] = []
    while True:
        job = claim_next(store, now=now())
        if job is None:
            if once:
                return processed
            time.sleep(poll_seconds)
            continue
        processed.append(process_job(config, job, store=store, client=client, analyzer=analyzer, log=log, now=now()))
