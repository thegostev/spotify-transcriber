"""Laptop shim: forward ``add`` and ``status`` to the Mac mini."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

import yaml

from podscribe.config import ConfigError

TRANSPORTS = ("rex", "ssh")
DEFAULT_TRANSPORT = "rex"
DEFAULT_COMMAND = "python -m podscribe"


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
