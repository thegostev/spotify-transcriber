"""A SQLite queue of episode links awaiting the one podscribe worker."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

QUEUE_FILENAME = "queue.db"
QUEUED = "queued"
RUNNING = "running"
DONE = "done"
UNMATCHED = "unmatched"
FAILED = "failed"

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


def _timestamp(now: datetime | None) -> str:
    """Return ``now`` as an ISO 8601 string with second precision."""
    return (now or datetime.now()).isoformat(timespec="seconds")


def _job(row: sqlite3.Row) -> Job:
    """Turn one jobs row into a Job."""
    return Job(**dict(row))


def enqueue(store: Store, url: str, *, now: datetime | None = None) -> EnqueueResult:
    """Add one episode link to the queue.

    Args:
        store: The queue database.
        url: Spotify episode link; unique in the queue.
        now: Creation time; defaults to the current time.

    Returns:
        Status ``new`` and the queued job.
    """
    connection = _connect(store)
    try:
        cursor = connection.execute(
            "INSERT INTO jobs (episode_url, state, created_at) VALUES (?, ?, ?)",
            (url, QUEUED, _timestamp(now)),
        )
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return EnqueueResult("new", _job(row))
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
