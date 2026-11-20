"""Tests for the SQLite queue of episode links."""

from __future__ import annotations

from datetime import datetime

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
