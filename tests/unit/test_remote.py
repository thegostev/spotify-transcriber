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


def test_load_remote_config_defaults_to_rex_without_a_host(tmp_path):
    from podscribe.remote import load_remote_config

    path = write_remote_config(tmp_path / "laptop.yaml", "remote:\n  rex_session: podscribe\n")

    remote = load_remote_config(path)

    assert remote.transport == "rex"
    assert remote.rex_host == ""


def test_load_remote_config_rejects_an_unknown_transport(tmp_path):
    from podscribe.remote import load_remote_config

    path = write_remote_config(tmp_path / "laptop.yaml", "remote:\n  transport: carrier-pigeon\n")

    with pytest.raises(ConfigError, match="transport"):
        load_remote_config(path)


def test_load_remote_config_needs_the_rex_session(tmp_path):
    from podscribe.remote import load_remote_config

    path = write_remote_config(tmp_path / "laptop.yaml", "remote:\n  transport: rex\n  rex_host: mini\n")

    with pytest.raises(ConfigError, match="rex_session"):
        load_remote_config(path)


def test_load_remote_config_needs_the_ssh_target(tmp_path):
    from podscribe.remote import load_remote_config

    path = write_remote_config(tmp_path / "laptop.yaml", "remote:\n  transport: ssh\n")

    with pytest.raises(ConfigError, match="ssh_target"):
        load_remote_config(path)


def test_remote_line_keeps_a_hostile_url_one_argument():
    from podscribe.remote import RemoteConfig, remote_line

    url = "https://open.spotify.com/episode/x; rm -rf ~ $(boom) `id`"
    remote = RemoteConfig(
        transport="rex", rex_host="mini", rex_session="p", ssh_target="h@m", command="uv run python -m podscribe"
    )

    line = remote_line(remote, "add", url)

    assert shlex.split(line) == ["uv", "run", "python", "-m", "podscribe", "add", url]


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


class FakeRunner:
    """Record each argv and serve queued results; empty stdout after that."""

    def __init__(self, *results):
        self.calls: list[list[str]] = []
        self.results = list(results)

    def __call__(self, argv):
        self.calls.append(list(argv))
        if self.results:
            return self.results.pop(0)
        return completed(argv, stdout="nothing printed yet\n")


class FakeClock:
    """Advance a tenth of a second on every read."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.1
        return self.now


def completed(argv, code: int = 0, *, stdout: str = "", stderr: str = ""):
    import subprocess

    return subprocess.CompletedProcess(list(argv), code, stdout, stderr)


def rex_remote(**overrides):
    from podscribe.remote import RemoteConfig

    values = {"transport": "rex", "rex_host": "mini", "rex_session": "podscribe", "ssh_target": "h@m"}
    values.update(overrides)
    return RemoteConfig(**values)


def status_screen(*lines: str) -> str:
    from podscribe.remote import STATUS_BEGIN, STATUS_END

    echoed = f"harald@mini bootstrap % echo {STATUS_BEGIN}; python -m podscribe status; echo {STATUS_END}"
    return "\n".join([echoed, STATUS_BEGIN, *lines, STATUS_END, "harald@mini bootstrap %"]) + "\n"


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_rex_send_types_the_line_and_submits_it():
    from podscribe.remote import send_add

    runner = FakeRunner(completed([], 0))
    send_add(rex_remote(), "https://open.spotify.com/episode/abc", run=runner)

    assert runner.calls == [
        ["rex", "-S", "mini", "send", "-s", "podscribe", "python -m podscribe add https://open.spotify.com/episode/abc\n"]
    ]


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_rex_send_omits_the_server_flag_without_a_host():
    from podscribe.remote import send_add

    runner = FakeRunner(completed([], 0))
    send_add(rex_remote(rex_host=""), "https://open.spotify.com/episode/abc", run=runner)

    assert runner.calls[0][:2] == ["rex", "send"]


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_rex_exit_three_names_the_session_create_command():
    import re

    from podscribe.remote import RemoteError, send_add

    failure = completed([], 3, stderr='session "podscribe" not found')
    with pytest.raises(RemoteError, match=re.escape("rex -S mini session new podscribe --keep-open")):
        send_add(rex_remote(), "https://open.spotify.com/episode/abc", run=FakeRunner(failure))


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_ssh_send_runs_the_line_as_one_argument():
    from podscribe.remote import send_add

    runner = FakeRunner(completed([], 0))
    send_add(rex_remote(transport="ssh"), "https://open.spotify.com/episode/abc", run=runner)

    assert runner.calls == [["ssh", "h@m", "--", "python -m podscribe add https://open.spotify.com/episode/abc"]]


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_rex_status_polls_the_screen_until_the_end_marker():
    from podscribe.remote import read_status

    runner = FakeRunner(
        completed([], 0),
        completed([], 0, stdout="harald@mini bootstrap % echo __podscribe_status_begin__\n"),
        completed([], 0, stdout=status_screen("done  /vault/note.md", "queued  https://x  (added 08:00)")),
    )

    output = read_status(rex_remote(), run=runner, clock=FakeClock(), sleep=lambda seconds: None)

    assert output == "done  /vault/note.md\nqueued  https://x  (added 08:00)"
    assert runner.calls[1][:2] == ["rex", "-S"]
    assert "--unwrap" in runner.calls[1]


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_rex_status_gives_up_after_the_timeout():
    from podscribe.remote import RemoteError, read_status

    runner = FakeRunner(completed([], 0))
    with pytest.raises(RemoteError, match="podscribe"):
        read_status(rex_remote(), run=runner, clock=FakeClock(), sleep=lambda seconds: None, timeout=0.5)


@pytest.mark.xfail(strict=True, reason="LAG-1053")
def test_ssh_status_returns_the_text_between_the_markers():
    from podscribe.remote import read_status

    runner = FakeRunner(completed([], 0, stdout=status_screen("failed  https://x  (download)")))

    output = read_status(rex_remote(transport="ssh"), run=runner)

    assert output == "failed  https://x  (download)"
