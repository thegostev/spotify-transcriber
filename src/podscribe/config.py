"""Load and validate podscribe's private config.yaml.

Every path, host, model and prompt lives in config.yaml (gitignored). Secrets
are not values here: llm.api_key carries Keychain references only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SECTIONS = ("paths", "intake", "analyzer", "speech", "llm", "notifications", "remote")
OPTIONAL_SECTIONS = ("speech", "llm")

REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "paths": ("output_dir", "failure_notes_dir", "data_dir", "log_file"),
    "intake": ("itunes_search_url", "match_window_days", "user_agent"),
    "analyzer": ("backend",),
    "notifications": ("macos",),
    "remote": ("transport", "rex_host", "rex_session", "ssh_target"),
}

ANALYZER_BACKENDS: dict[str, tuple[str, ...]] = {
    "superwhisper": ("wf_path", "mode_key"),
    "command": ("argv",),
    "module": ("path",),
}

DEFAULT_CONFIG_PATH = Path("config.yaml")


class ConfigError(Exception):
    """The config file is missing, unreadable or incomplete."""


@dataclass(frozen=True, slots=True)
class Config:
    """The validated config, one attribute per top-level section.

    Attributes:
        paths: Vault and runtime paths, with ``~`` expanded.
        analyzer: Backend selection and its per-backend settings.
        speech: Legacy speech plans; optional, ``{}`` when absent.
        llm: Legacy Ollama Cloud passes; optional, ``{}`` when absent.
        source: The file the config was read from.
    """

    paths: dict[str, Any]
    intake: dict[str, Any]
    analyzer: dict[str, Any]
    speech: dict[str, Any]
    llm: dict[str, Any]
    notifications: dict[str, Any]
    remote: dict[str, Any]
    source: Path


def _validate_analyzer(analyzer: dict[str, Any], source: Path) -> None:
    """Check the backend name and its settings, so failures happen at startup."""
    backend = analyzer["backend"]
    if not isinstance(backend, str):
        raise ConfigError(f"config file {source} needs a string analyzer.backend")
    if backend not in ANALYZER_BACKENDS:
        expected = ", ".join(ANALYZER_BACKENDS)
        raise ConfigError(f"config file {source} has unknown analyzer.backend {backend!r}; expected {expected}")
    options = analyzer.get(backend)
    if not isinstance(options, dict):
        raise ConfigError(f"config file {source} is missing section analyzer.{backend}")
    for key in ANALYZER_BACKENDS[backend]:
        if key not in options:
            raise ConfigError(f"config file {source} is missing key analyzer.{backend}.{key}")
    if "timeout_seconds" in options:
        timeout = options["timeout_seconds"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ConfigError(f"config file {source} needs a number analyzer.{backend}.timeout_seconds")
    if backend == "command":
        argv = options["argv"]
        if not isinstance(argv, list) or not argv:
            raise ConfigError(f"config file {source} needs a non-empty list analyzer.command.argv")
        if not any("{audio}" in str(part) for part in argv):
            raise ConfigError(f"config file {source} needs {{audio}} in analyzer.command.argv")


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> Config:
    """Read config.yaml, expand path tildes and validate required keys.

    ``speech`` and ``llm`` are legacy sections: loaded when present, ``{}``
    when absent. The ``analyzer`` section and its backend settings are required.

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
        if values is None and section in OPTIONAL_SECTIONS:
            values = {}
        if not isinstance(values, dict):
            raise ConfigError(f"config file {source} is missing section {section}")
        for key in REQUIRED_KEYS.get(section, ()):
            if key not in values:
                raise ConfigError(f"config file {source} is missing key {section}.{key}")
        sections[section] = values
    _validate_analyzer(sections["analyzer"], source)
    paths = {key: str(Path(str(value)).expanduser()) for key, value in sections["paths"].items()}
    return Config(paths=paths, source=source, **{name: sections[name] for name in SECTIONS if name != "paths"})
