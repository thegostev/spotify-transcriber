"""A SQLite queue of episode links awaiting the one podscribe worker."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

QUEUE_FILENAME = "queue.db"

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
