"""Laptop shim: forward ``add`` and ``status`` to the Mac mini."""

from __future__ import annotations

import secrets
import shlex
import subprocess
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import yaml

from podscribe.config import ConfigError

TRANSPORTS = ("rex", "ssh")
DEFAULT_TRANSPORT = "rex"
DEFAULT_COMMAND = "python -m podscribe"
STATUS_BEGIN = "__podscribe_status_begin_"
STATUS_END = "__podscribe_status_end_"
REX_MISSING_TARGET = 3
STATUS_TIMEOUT_SECONDS = 30.0
POLL_SECONDS = 0.2
Result = subprocess.CompletedProcess[str]


@dataclass(frozen=True, slots=True)
class RemoteConfig:
    """Far-side settings; an empty ``rex_host`` means this machine's server."""

    transport: str
    rex_host: str
    rex_session: str
    ssh_target: str
    command: str = DEFAULT_COMMAND
    cwd: str | None = None


def load_remote_config(path: Path | str) -> RemoteConfig:
    """Read the ``remote`` section of a laptop config; other sections are ignored.

    Args:
        path: Config file; ``~`` is expanded.

    Returns:
        The validated settings.

    Raises:
        ConfigError: The section, transport or a required key is missing.
    """
    source = Path(path).expanduser()
    if not source.is_file():
        raise ConfigError(f"config file not found: {source}")
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("remote"), dict):
        raise ConfigError(f"config file {source} is missing section remote")
    remote = raw["remote"]
    transport = remote.get("transport", DEFAULT_TRANSPORT)
    if transport not in TRANSPORTS:
        raise ConfigError(f"config file {source} has unknown remote.transport {transport!r}; expected rex, ssh")
    if transport == "rex" and not remote.get("rex_session"):
        raise ConfigError(f"config file {source} is missing key remote.rex_session")
    if transport == "ssh" and not remote.get("ssh_target"):
        raise ConfigError(f"config file {source} is missing key remote.ssh_target")
    command = remote.get("command", DEFAULT_COMMAND)
    if not isinstance(command, str) or not command.strip():
        raise ConfigError(f"config file {source} needs a non-empty remote.command")
    return RemoteConfig(
        transport=transport, rex_host=str(remote.get("rex_host") or ""),
        rex_session=str(remote.get("rex_session") or ""), ssh_target=str(remote.get("ssh_target") or ""),
        command=command, cwd=str(remote["cwd"]) if remote.get("cwd") else None,
    )


def remote_line(remote: RemoteConfig, *args: str) -> str:
    """Build the far-side command line, quoting every word for the shell.

    Args:
        remote: Far-side settings.
        *args: Words appended after ``remote.command``.

    Returns:
        One shell command line; an episode link stays a single argument.
    """
    command = shlex.join([*shlex.split(remote.command), *args])
    return f"cd {shlex.quote(remote.cwd)} && {command}" if remote.cwd else command


class RemoteError(Exception):
    """The far side could not be reached, or its answer was unreadable."""


run_subprocess = partial(subprocess.run, capture_output=True, text=True, check=False)


def _checked(result: Result, remote: RemoteConfig, action: str) -> Result:
    """Return a successful result, otherwise raise RemoteError with a next step."""
    if result.returncode == 0:
        return result
    if result.returncode == REX_MISSING_TARGET:
        server = f"-S {remote.rex_host} " if remote.rex_host else ""
        raise RemoteError(f"rex exit 3: host {remote.rex_host!r} or session {remote.rex_session!r} missing; "
                          f"create it with: rex {server}session new {remote.rex_session} --keep-open")
    raise RemoteError(f"{action} failed (exit {result.returncode}): {(result.stderr or result.stdout).strip()}")


def _rex_argv(remote: RemoteConfig, verb: str, *options: str) -> list[str]:
    """Build a Rex command for the configured server."""
    return ["rex", *(("-S", remote.rex_host) if remote.rex_host else ()), verb, *options]


def rex_call(
    remote: RemoteConfig, line: str, *, wait: bool, run=run_subprocess, begin: str = "", end: str = ""
) -> str:
    """Type the line into the Rex session; poll the screen when ``wait``."""
    _checked(run(_rex_argv(remote, "send", "-s", remote.rex_session, line + "\n")), remote, "rex send")
    if not wait:
        return ""
    deadline = time.monotonic() + STATUS_TIMEOUT_SECONDS
    capture = _rex_argv(remote, "capture", "-s", remote.rex_session, "--unwrap", "--trim")
    while True:
        found = between_markers(_checked(run(capture), remote, "rex capture").stdout, begin, end)
        if found is not None:
            return found
        if time.monotonic() >= deadline:
            raise RemoteError(f"rex capture: session {remote.rex_session!r} printed no status "
                              f"within {STATUS_TIMEOUT_SECONDS:.0f}s")
        time.sleep(POLL_SECONDS)


def ssh_call(remote: RemoteConfig, line: str, *, wait: bool, run=run_subprocess, begin: str = "", end: str = "") -> str:
    """Run the line over ssh; when ``wait``, return the output between the markers."""
    result = _checked(run(["ssh", remote.ssh_target, "--", line]), remote, "ssh")
    return (between_markers(result.stdout, begin, end) or "") if wait else ""


def between_markers(screen: str, begin: str, end: str) -> str | None:
    """Return what the far side printed between these two markers, if both are there."""
    lines = screen.splitlines()
    starts = [index for index, text in enumerate(lines) if text.strip() == begin]
    for start in reversed(starts):
        ends = [index for index in range(start + 1, len(lines)) if lines[index].strip() == end]
        if ends:
            return "\n".join(lines[start + 1 : ends[0]])
    return None


TRANSPORT_CALLS = {"rex": rex_call, "ssh": ssh_call}


def send_add(remote: RemoteConfig, url: str, **options) -> None:
    """Forward ``add <url>`` to the configured transport and return at once."""
    TRANSPORT_CALLS[remote.transport](remote, remote_line(remote, "add", url), wait=False, **options)


def read_status(remote: RemoteConfig, *, token: str | None = None, **options) -> str:
    """Forward ``status`` and return the output between this call's markers.

    A fresh token keeps an older status, still visible in the terminal
    scrollback, from being mistaken for this call's answer.
    """
    token = token or secrets.token_hex(8)
    begin, end = f"{STATUS_BEGIN}{token}__", f"{STATUS_END}{token}__"
    line = f"echo {begin}; {remote_line(remote, 'status')}; echo {end}"
    return TRANSPORT_CALLS[remote.transport](remote, line, wait=True, begin=begin, end=end, **options)
