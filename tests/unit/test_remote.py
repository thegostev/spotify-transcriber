"""Tests for the laptop shim: forward ``add`` and ``status`` to the Mac mini."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from podscribe.config import ConfigError


def write_remote_config(path: Path, text: str) -> Path:
    """Write a laptop config file and return its path."""
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_load_remote_config_reads_a_laptop_config(tmp_path):
    from podscribe.remote import load_remote_config

    path = write_remote_config(
        tmp_path / "laptop.yaml",
        "remote:\n  transport: rex\n  rex_host: mini\n  rex_session: podscribe\n  ssh_target: h@m\n",
    )

    remote = load_remote_config(path)

    assert remote.transport == "rex"
    assert remote.rex_host == "mini"
    assert remote.rex_session == "podscribe"
    assert remote.ssh_target == "h@m"
    assert remote.command == "python -m podscribe"
    assert remote.cwd is None


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_load_remote_config_defaults_to_rex_without_a_host(tmp_path):
    from podscribe.remote import load_remote_config

    path = write_remote_config(tmp_path / "laptop.yaml", "remote:\n  rex_session: podscribe\n")

    remote = load_remote_config(path)

    assert remote.transport == "rex"
    assert remote.rex_host == ""


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_load_remote_config_rejects_an_unknown_transport(tmp_path):
    from podscribe.remote import load_remote_config

    path = write_remote_config(tmp_path / "laptop.yaml", "remote:\n  transport: carrier-pigeon\n")

    with pytest.raises(ConfigError, match="transport"):
        load_remote_config(path)


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_load_remote_config_needs_the_rex_session(tmp_path):
    from podscribe.remote import load_remote_config

    path = write_remote_config(tmp_path / "laptop.yaml", "remote:\n  transport: rex\n  rex_host: mini\n")

    with pytest.raises(ConfigError, match="rex_session"):
        load_remote_config(path)


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_load_remote_config_needs_the_ssh_target(tmp_path):
    from podscribe.remote import load_remote_config

    path = write_remote_config(tmp_path / "laptop.yaml", "remote:\n  transport: ssh\n")

    with pytest.raises(ConfigError, match="ssh_target"):
        load_remote_config(path)


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_remote_line_keeps_a_hostile_url_one_argument():
    from podscribe.remote import RemoteConfig, remote_line

    url = "https://open.spotify.com/episode/x; rm -rf ~ $(boom) `id`"
    remote = RemoteConfig(
        transport="rex", rex_host="mini", rex_session="p", ssh_target="h@m", command="uv run python -m podscribe"
    )

    line = remote_line(remote, "add", url)

    assert shlex.split(line) == ["uv", "run", "python", "-m", "podscribe", "add", url]


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_remote_line_changes_into_the_configured_directory():
    from podscribe.remote import RemoteConfig, remote_line

    remote = RemoteConfig(
        transport="rex",
        rex_host="mini",
        rex_session="p",
        ssh_target="h@m",
        command="python -m podscribe",
        cwd="/Users/harald/My Repo",
    )

    line = remote_line(remote, "status")

    assert shlex.split(line) == ["cd", "/Users/harald/My Repo", "&&", "python", "-m", "podscribe", "status"]
