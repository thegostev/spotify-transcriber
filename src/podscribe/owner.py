"""The owner file that names the job inside the shared Superwhisper analyzer."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

OWNER_FILENAME = "analyzing.json"


def owner_path(data_dir: Path | str) -> Path:
    """Return the owner file path inside the worker's data directory."""
    return Path(data_dir).expanduser() / OWNER_FILENAME


def write_owner(path: Path | str, job_id: int, *, now: datetime | None = None, pid: int | None = None) -> None:
    """Record that ``pid`` is analyzing ``job_id``.

    Args:
        path: The owner file; any previous file is replaced.
        job_id: The queue row the analyzer is working on.
        now: Start time; defaults to the current time.
        pid: Owner process; defaults to this process.
    """
    payload = {
        "pid": os.getpid() if pid is None else pid,
        "job": job_id,
        "since": (now or datetime.now()).isoformat(timespec="seconds"),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")


def clear_owner(path: Path | str) -> None:
    """Remove the owner file; a missing file is not an error."""
    Path(path).unlink(missing_ok=True)


def _alive(pid: int) -> bool:
    """Return whether a process with ``pid`` still exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def owner_job(path: Path | str) -> int | None:
    """Return the job id in a live owner file, None when absent or stale."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    pid, job = payload.get("pid"), payload.get("job")
    if not isinstance(pid, int) or not isinstance(job, int):
        return None
    return job if _alive(pid) else None
