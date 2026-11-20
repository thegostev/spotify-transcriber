"""Tests for the LaunchAgent that keeps the queue worker running."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path


def test_render_plist_describes_the_worker(tmp_path, config_factory, monkeypatch):
    from podscribe.service import render_plist

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config = config_factory()
    config_path = tmp_path / "config.yaml"
    plist = plistlib.loads(
        render_plist(config, config_path=config_path, log_file="~/logs/podscribe.log").encode("utf-8")
    )

    assert plist["Label"] == "com.podscribe.worker"
    assert plist["ProgramArguments"][:3] == [sys.executable, "-m", "podscribe"]
    assert plist["ProgramArguments"][3:] == ["run", "--config", str(config_path.resolve())]
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert plist["WorkingDirectory"] == str(Path(config.paths["data_dir"]).resolve())
    assert plist["StandardOutPath"] == str(tmp_path / "home" / "logs" / "podscribe.log")
    assert plist["StandardErrorPath"] == plist["StandardOutPath"]


def test_install_service_dry_run_writes_nothing(tmp_path, config_factory):
    from podscribe.service import install_service

    target = tmp_path / "LaunchAgents" / "com.podscribe.worker.plist"

    result = install_service(
        config_factory(),
        config_path=tmp_path / "config.yaml",
        log_file=tmp_path / "podscribe.log",
        target=target,
        dry_run=True,
    )

    assert result == target
    assert not target.exists()


def test_install_service_writes_the_plist(tmp_path, config_factory):
    from podscribe.service import install_service

    target = tmp_path / "LaunchAgents" / "com.podscribe.worker.plist"

    result = install_service(
        config_factory(),
        config_path=tmp_path / "config.yaml",
        log_file=tmp_path / "podscribe.log",
        target=target,
    )

    assert result == target
    assert plistlib.loads(target.read_bytes())["Label"] == "com.podscribe.worker"
