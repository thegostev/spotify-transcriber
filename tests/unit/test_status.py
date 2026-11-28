"""Tests for the status listing and the shared Superwhisper lock probe."""

from __future__ import annotations

import fcntl
from datetime import datetime

import pytest

from podscribe.queue import Job

URL = "https://open.spotify.com/episode/abc123"


def test_format_status_lists_every_state():
    from podscribe.cli import format_status

    jobs = [
        Job(id=5, episode_url="done-url", state="done", note_path="/notes/episode.md"),
        Job(id=4, episode_url="failed-url", state="failed", reason="analyzer boom"),
        Job(id=3, episode_url="unmatched-url", state="unmatched", reason="unmatched episode: Another"),
        Job(id=2, episode_url="queued-url", state="queued", created_at="2026-11-20T12:01:00"),
    ]

    assert format_status(jobs, lock_held=lambda: False) == [
        "done  /notes/episode.md",
        "failed  failed-url  (analyzer boom)",
        "unmatched  unmatched-url  (unmatched episode: Another)",
        "queued  queued-url  (added 12:01)",
    ]


def test_format_status_flags_a_running_job_while_superwhisper_is_locked():
    from podscribe.cli import format_status

    jobs = [Job(id=1, episode_url=URL, state="running", started_at="2026-11-20T12:05:00")]

    assert format_status(jobs, lock_held=lambda: True) == [
        f"running  {URL}  (started 12:05)  waiting for Superwhisper"
    ]
    assert format_status(jobs, lock_held=lambda: False) == [f"running  {URL}  (started 12:05)"]


def test_superwhisper_lock_probe_sees_a_held_lock(tmp_path):
    from podscribe.cli import superwhisper_lock_held

    path = tmp_path / "superwhisper.lock"
    path.write_text("", encoding="utf-8")
    assert superwhisper_lock_held(path) is False

    with path.open("r") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            assert superwhisper_lock_held(path) is True
        finally:
            handle.close()

    assert superwhisper_lock_held(path) is False


def test_superwhisper_lock_probe_treats_a_missing_file_as_free(tmp_path):
    from podscribe.cli import superwhisper_lock_held

    assert superwhisper_lock_held(tmp_path / "missing.lock") is False


def test_main_status_prints_the_queue_without_building_the_analyzer(config_factory, capsys, monkeypatch):
    import podscribe.cli as cli
    from podscribe.queue import enqueue, open_store

    config = config_factory()
    enqueue(open_store(config.paths["data_dir"]), URL, now=datetime(2026, 11, 20, 12, 1, 0))

    def explode(*args, **kwargs):
        raise AssertionError("analyzer built for status")

    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "build_analyzer", explode)
    monkeypatch.setattr(cli, "superwhisper_lock_held", lambda: False)

    assert cli.main(["status"]) == 0
    assert capsys.readouterr().out == f"queued  {URL}  (added 12:01)\n"


@pytest.mark.xfail(strict=True, reason="LAG-1062")
def test_format_status_says_analyzing_when_podscribe_holds_the_lock():
    from podscribe.cli import format_status

    jobs = [Job(id=1, episode_url=URL, state="running", started_at="2026-11-20T12:05:00")]

    assert format_status(jobs, lock_held=lambda: True, analyzing_job=1) == [
        f"running  {URL}  (started 12:05)  analyzing"
    ]


@pytest.mark.xfail(strict=True, reason="LAG-1062")
def test_main_status_names_the_running_job_that_holds_the_lock(config_factory, capsys, monkeypatch):
    import os

    import podscribe.cli as cli
    from podscribe.owner import owner_path, write_owner
    from podscribe.queue import claim_next, enqueue, open_store

    config = config_factory()
    store = open_store(config.paths["data_dir"])
    enqueue(store, URL, now=datetime(2026, 11, 20, 12, 1, 0))
    job = claim_next(store, now=datetime(2026, 11, 20, 12, 5, 0))
    write_owner(owner_path(config.paths["data_dir"]), job.id, pid=os.getpid())

    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "superwhisper_lock_held", lambda: True)

    assert cli.main(["status"]) == 0
    assert capsys.readouterr().out == f"running  {URL}  (started 12:05)  analyzing\n"


@pytest.mark.xfail(strict=True, reason="LAG-1062")
def test_main_status_still_waits_when_the_owner_file_is_stale(config_factory, capsys, monkeypatch):
    import podscribe.cli as cli
    from podscribe.owner import owner_path, write_owner
    from podscribe.queue import claim_next, enqueue, open_store

    config = config_factory()
    store = open_store(config.paths["data_dir"])
    enqueue(store, URL, now=datetime(2026, 11, 20, 12, 1, 0))
    job = claim_next(store, now=datetime(2026, 11, 20, 12, 5, 0))
    write_owner(owner_path(config.paths["data_dir"]), job.id, pid=999_999)

    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "superwhisper_lock_held", lambda: True)

    assert cli.main(["status"]) == 0
    assert capsys.readouterr().out == f"running  {URL}  (started 12:05)  waiting for Superwhisper\n"
