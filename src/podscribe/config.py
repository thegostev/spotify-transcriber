"""Load and validate podscribe's private config.yaml.

Every path, host, model and prompt lives in config.yaml (gitignored). Secrets
are not values here: llm.api_key carries Keychain references only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SECTIONS = ("paths", "intake", "speech", "llm", "notifications", "remote")

REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "paths": ("output_dir", "failure_notes_dir", "data_dir", "log_file"),
    "intake": ("itunes_search_url", "match_window_days", "user_agent"),
    "speech": ("language", "chunk_seconds", "plan1", "plan2"),
    "llm": ("host", "model", "api_key", "timeout_seconds", "retry_backoff_seconds", "cleanup", "summary"),
    "notifications": ("macos",),
    "remote": ("transport", "rex_host", "rex_session", "ssh_target"),
}

DEFAULT_CONFIG_PATH = Path("config.yaml")


class ConfigError(Exception):
    """The config file is missing, unreadable or incomplete."""


@dataclass(frozen=True, slots=True)
class Config:
    """The validated config, one attribute per top-level section.

    Attributes:
        paths: Vault and runtime paths, with ``~`` expanded.
        source: The file the config was read from.
    """

    paths: dict[str, Any]
    intake: dict[str, Any]
    speech: dict[str, Any]
    llm: dict[str, Any]
    notifications: dict[str, Any]
    remote: dict[str, Any]
    source: Path


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> Config:
    """Read config.yaml, expand path tildes and validate required keys.

    Args:
        path: Location of the config file; ``~`` is expanded.

    Returns:
        The validated config.

    Raises:
        ConfigError: The file is missing, is not a mapping, or lacks a key.
    """
    source = Path(path).expanduser()
    if not source.is_file():
        raise ConfigError(f"config file not found: {source}")
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError(f"config file {source} must contain a mapping of sections")
    sections: dict[str, dict[str, Any]] = {}
    for section in SECTIONS:
        values = raw.get(section)
        if not isinstance(values, dict):
            raise ConfigError(f"config file {source} is missing section {section}")
        for key in REQUIRED_KEYS[section]:
            if key not in values:
                raise ConfigError(f"config file {source} is missing key {section}.{key}")
        sections[section] = values
    paths = {key: str(Path(str(value)).expanduser()) for key, value in sections["paths"].items()}
    return Config(paths=paths, source=source, **{name: sections[name] for name in SECTIONS if name != "paths"})
