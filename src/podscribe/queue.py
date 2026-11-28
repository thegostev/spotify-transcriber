"""A SQLite queue of episode links awaiting the one podscribe worker."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from podscribe.links import canonical_episode_url

QUEUE_FILENAME = "queue.db"
QUEUED = "queued"
RUNNING = "running"
DONE = "done"
UNMATCHED = "unmatched"
FAILED = "failed"
STALE_RUN = timedelta(hours=6)
STALE_REASON = "requeued after a stale run"

_DUPLICATE_STATUS = {DONE: "already_done", QUEUED: "already_queued", RUNNING: "already_running"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_url TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    note_path TEXT,
    reason TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
)
"""


@dataclass(frozen=True, slots=True)
class Job:
    """One episode link and where it is in the queue."""

    id: int
    episode_url: str
    state: str
    note_path: str | None = None
    reason: str | None = None
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    """What enqueueing one link changed: a status and the resulting job."""

    status: str
    job: Job


@dataclass(frozen=True, slots=True)
class Store:
    """Location of the queue database; its parent is created on demand."""

    path: Path


def open_store(data_dir: Path | str) -> Store:
    """Return the queue store at ``data_dir/queue.db``, creating the directory."""
    path = Path(data_dir).expanduser() / QUEUE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return Store(path)


def _connect(store: Store) -> sqlite3.Connection:
    """Open the store and make sure the jobs table exists."""
    Path(store.path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(store.path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute(_SCHEMA)
    return connection


def _started(stamp: str | None) -> datetime | None:
    """Return the parseable start time of a job, None when absent or bad."""
    try:
        return datetime.fromisoformat(stamp) if stamp else None
    except ValueError:
        return None


def _timestamp(now: datetime | None) -> str:
    """Return ``now`` as an ISO 8601 string with second precision."""
    return (now or datetime.now()).isoformat(timespec="seconds")


def _duplicate_status(state: str) -> str:
    """Return the enqueue status for a link that is already in the queue."""
    return _DUPLICATE_STATUS.get(state, "retry")


def _job(row: sqlite3.Row) -> Job:
    """Turn one jobs row into a Job."""
    return Job(**dict(row))


def _find_job(connection: sqlite3.Connection, canonical: str) -> sqlite3.Row | None:
    """Return the job for an episode, matching a stored link that has tracking.

    Older rows kept the link as submitted, so a row carrying ``?si=`` would
    otherwise look like a new episode. A matched row is rewritten to the
    canonical form.
    """
    row = connection.execute("SELECT * FROM jobs WHERE episode_url = ?", (canonical,)).fetchone()
    if row is not None:
        return row
    for candidate in connection.execute("SELECT id, episode_url FROM jobs ORDER BY id"):
        if canonical_episode_url(candidate["episode_url"]) != canonical:
            continue
        connection.execute("UPDATE jobs SET episode_url = ? WHERE id = ?", (canonical, candidate["id"]))
        return connection.execute("SELECT * FROM jobs WHERE id = ?", (candidate["id"],)).fetchone()
    return None


def enqueue(store: Store, url: str, *, now: datetime | None = None) -> EnqueueResult:
    """Add one episode link to the queue.

    Args:
        store: The queue database.
        url: Episode link; its canonical form is unique in the queue.
        now: Creation time; defaults to the current time.

    Returns:
        ``new`` or ``retry`` with a queued job, or ``already_done``,
        ``already_queued`` or ``already_running`` with the existing job.
    """
    canonical = canonical_episode_url(url)
    connection = _connect(store)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _find_job(connection, canonical)
        if row is None:
            cursor = connection.execute(
                "INSERT INTO jobs (episode_url, state, created_at) VALUES (?, ?, ?)",
                (canonical, QUEUED, _timestamp(now)),
            )
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (cursor.lastrowid,)).fetchone()
            status = "new"
        else:
            current = _job(row)
            status = _duplicate_status(current.state)
            if status == "retry":
                connection.execute(
                    "UPDATE jobs SET state = ?, reason = NULL, started_at = NULL, finished_at = NULL WHERE id = ?",
                    (QUEUED, current.id),
                )
                row = connection.execute("SELECT * FROM jobs WHERE id = ?", (current.id,)).fetchone()
        connection.execute("COMMIT")
        return EnqueueResult(status, _job(row))
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def list_jobs(store: Store, *, limit: int = 50) -> list[Job]:
    """Return the newest jobs first, at most ``limit`` of them."""
    connection = _connect(store)
    try:
        rows = connection.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_job(row) for row in rows]
    finally:
        connection.close()


def claim_next(store: Store, *, now: datetime | None = None) -> Job | None:
    """Claim the oldest queued job and mark it running.

    Args:
        store: The queue database.
        now: Start time; defaults to the current time.

    Returns:
        The claimed job, or None when no job is queued.
    """
    connection = _connect(store)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id FROM jobs WHERE state = ? ORDER BY id LIMIT 1", (QUEUED,)
        ).fetchone()
        if row is None:
            connection.execute("COMMIT")
            return None
        connection.execute(
            "UPDATE jobs SET state = ?, started_at = ? WHERE id = ?",
            (RUNNING, _timestamp(now), row["id"]),
        )
        job = _job(connection.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone())
        connection.execute("COMMIT")
        return job
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def finish(
    store: Store,
    job: Job,
    state: str,
    *,
    note_path: Path | str | None = None,
    reason: str | None = None,
    now: datetime | None = None,
) -> Job:
    """Record how one claimed job ended.

    Args:
        store: The queue database.
        job: The claimed job.
        state: Final state: done, unmatched or failed.
        note_path: Episode note written for a done job.
        reason: Why an unmatched or failed job stopped.
        now: Finish time; defaults to the current time.

    Returns:
        The job as stored after the update.

    Raises:
        ValueError: ``state`` is not a final state.
    """
    if state not in (DONE, UNMATCHED, FAILED):
        raise ValueError(f"not a final job state: {state}")
    connection = _connect(store)
    try:
        connection.execute(
            "UPDATE jobs SET state = ?, note_path = ?, reason = ?, finished_at = ? WHERE id = ?",
            (state, str(note_path) if note_path else None, reason, _timestamp(now), job.id),
        )
        return _job(connection.execute("SELECT * FROM jobs WHERE id = ?", (job.id,)).fetchone())
    finally:
        connection.close()


def requeue_stale(
    store: Store, *, older_than: timedelta = STALE_RUN, now: datetime | None = None
) -> list[Job]:
    """Return running jobs older than ``older_than`` to the queue.

    A worker killed mid-episode leaves its row running forever, so the episode
    can never be claimed again. The worker calls this once at startup; a row
    with no readable start time counts as stale.

    Args:
        store: The queue database.
        older_than: How long a run may last before it is assumed dead.
        now: Current time; defaults to the current time.

    Returns:
        The jobs that were requeued, oldest first.
    """
    cutoff = (now or datetime.now()) - older_than
    connection = _connect(store)
    try:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT * FROM jobs WHERE state = ? ORDER BY id", (RUNNING,)
        ).fetchall()
        reclaimed = []
        for row in rows:
            started = _started(row["started_at"])
            if started is not None and started > cutoff:
                continue
            connection.execute(
                "UPDATE jobs SET state = ?, reason = ?, started_at = NULL, finished_at = NULL WHERE id = ?",
                (QUEUED, STALE_REASON, row["id"]),
            )
            reclaimed.append(_job(connection.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone()))
        connection.execute("COMMIT")
        return reclaimed
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
