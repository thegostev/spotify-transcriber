"""Shared fixtures for the unit tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from podscribe.config import Config


@pytest.fixture
def config_factory(tmp_path: Path) -> Callable[..., Config]:
    """Return a factory that builds a Config with temp paths, no network."""

    def make(*, output: Path | None = None, data_dir: Path | None = None, log_file: Path | None = None) -> Config:
        output_dir = output or tmp_path / "out"
        output_dir.mkdir(parents=True, exist_ok=True)
        data = data_dir or tmp_path / "data"
        return Config(
            paths={
                "output_dir": str(output_dir),
                "failure_notes_dir": str(tmp_path / "failures"),
                "data_dir": str(data),
                "log_file": str(log_file or data / "podscribe.log"),
            },
            intake={
                "itunes_search_url": "https://itunes.example/search",
                "match_window_days": 2,
                "user_agent": "podscribe-test",
            },
            analyzer={"backend": "command", "command": {"argv": ["fake"]}},
            speech={},
            llm={},
            notifications={"macos": False},
            remote={"transport": "rex", "rex_host": "mini", "rex_session": "p", "ssh_target": "h@m"},
            source=tmp_path / "config.yaml",
        )

    return make
