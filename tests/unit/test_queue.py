"""Tests for the SQLite queue of episode links."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

URL = "https://open.spotify.com/episode/abc123"


def test_open_store_places_the_database_in_the_data_dir(tmp_path, config_factory):
    from podscribe.queue import open_store

    store = open_store(config_factory().paths["data_dir"])

    assert store.path == tmp_path / "data" / "queue.db"
    assert store.path.parent.is_dir()


def test_enqueue_adds_a_queued_job(config_factory):
    from podscribe.queue import enqueue, open_store

    store = open_store(config_factory().paths["data_dir"])
    result = enqueue(store, URL, now=datetime(2026, 11, 20, 12, 1, 0))

    assert result.status == "new"
    assert result.job.episode_url == URL
    assert result.job.state == "queued"
    assert result.job.note_path is None
    assert result.job.created_at == "2026-11-20T12:01:00"


def test_list_jobs_returns_the_newest_first(config_factory):
    from podscribe.queue import enqueue, list_jobs, open_store

    store = open_store(config_factory().paths["data_dir"])
    first = enqueue(store, URL).job
    second = enqueue(store, URL + "-two").job

    jobs = list_jobs(store)

    assert [job.id for job in jobs] == [second.id, first.id]
    assert [job.episode_url for job in jobs] == [URL + "-two", URL]


def test_enqueue_skips_a_link_that_is_already_done(config_factory):
    from podscribe.queue import claim_next, enqueue, finish, open_store

    store = open_store(config_factory().paths["data_dir"])
    enqueue(store, URL)
    job = claim_next(store)
    finish(store, job, "done", note_path=Path("/notes/episode.md"))

    result = enqueue(store, URL)

    assert result.status == "already_done"
    assert result.job.note_path == "/notes/episode.md"


def test_enqueue_reports_a_queued_or_running_link(config_factory):
    from podscribe.queue import claim_next, enqueue, open_store

    store = open_store(config_factory().paths["data_dir"])
    enqueue(store, URL)

    assert enqueue(store, URL).status == "already_queued"
    claim_next(store)
    assert enqueue(store, URL).status == "already_running"


def test_enqueue_retries_a_failed_link(config_factory):
    from podscribe.queue import claim_next, enqueue, finish, open_store

    store = open_store(config_factory().paths["data_dir"])
    enqueue(store, URL)
    finish(store, claim_next(store), "failed", reason="boom")

    result = enqueue(store, URL)

    assert result.status == "retry"
    assert result.job.state == "queued"
    assert result.job.reason is None
    assert result.job.started_at is None
    assert result.job.finished_at is None


def test_claim_next_marks_the_oldest_job_running(config_factory):
    from podscribe.queue import claim_next, enqueue, open_store

    store = open_store(config_factory().paths["data_dir"])
    first = enqueue(store, URL).job
    second = enqueue(store, URL + "-two").job

    claimed = claim_next(store, now=datetime(2026, 11, 20, 12, 5, 0))

    assert claimed.id == first.id
    assert claimed.state == "running"
    assert claimed.started_at == "2026-11-20T12:05:00"
    assert claim_next(store).id == second.id
    assert claim_next(store) is None


def test_finish_records_the_final_state_and_time(config_factory):
    from podscribe.queue import claim_next, enqueue, finish, list_jobs, open_store

    store = open_store(config_factory().paths["data_dir"])
    enqueue(store, URL)
    job = claim_next(store)

    finished = finish(
        store, job, "unmatched", reason="unmatched episode: Another", now=datetime(2026, 11, 20, 12, 9, 0)
    )

    assert finished.state == "unmatched"
    assert finished.reason == "unmatched episode: Another"
    assert finished.finished_at == "2026-11-20T12:09:00"
    assert list_jobs(store)[0] == finished
