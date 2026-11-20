"""Tests for the SQLite queue of episode links."""

from __future__ import annotations

URL = "https://open.spotify.com/episode/abc123"


def test_open_store_places_the_database_in_the_data_dir(tmp_path, config_factory):
    from podscribe.queue import open_store

    store = open_store(config_factory().paths["data_dir"])

    assert store.path == tmp_path / "data" / "queue.db"
    assert store.path.parent.is_dir()
