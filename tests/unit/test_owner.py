"""Tests for the owner file that names the job inside the analyzer."""

from __future__ import annotations

import json
import os
from datetime import datetime

import pytest

FIXED_NOW = datetime(2026, 11, 20, 12, 0, 0)
DEAD_PID = 999_999


@pytest.mark.xfail(strict=True, reason="LAG-1062")
def test_write_owner_records_the_pid_job_and_time(tmp_path):
    from podscribe.owner import owner_job, owner_path, write_owner

    path = owner_path(tmp_path)
    write_owner(path, 7, now=FIXED_NOW, pid=os.getpid())

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "pid": os.getpid(),
        "job": 7,
        "since": "2026-11-20T12:00:00",
    }
    assert owner_job(path) == 7


@pytest.mark.xfail(strict=True, reason="LAG-1062")
def test_owner_job_ignores_a_dead_pid(tmp_path):
    from podscribe.owner import owner_job, owner_path, write_owner

    path = owner_path(tmp_path)
    write_owner(path, 7, pid=DEAD_PID)

    assert owner_job(path) is None


@pytest.mark.xfail(strict=True, reason="LAG-1062")
def test_owner_job_ignores_a_missing_or_broken_file(tmp_path):
    from podscribe.owner import owner_job, owner_path

    path = owner_path(tmp_path)
    assert owner_job(path) is None

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    assert owner_job(path) is None
