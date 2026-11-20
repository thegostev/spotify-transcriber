"""Render and install the LaunchAgent that keeps the podscribe worker running."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

from podscribe.config import Config

SERVICE_LABEL = "com.podscribe.worker"
LAUNCH_AGENTS_DIR = Path("~/Library/LaunchAgents")


def launch_agent_path() -> Path:
    """Return the user's LaunchAgents path for the worker plist."""
    return LAUNCH_AGENTS_DIR.expanduser() / f"{SERVICE_LABEL}.plist"


def render_plist(config: Config, *, config_path: Path | str, log_file: Path | str) -> str:
    """Render the worker's LaunchAgent plist with absolute paths.

    Args:
        config: Validated configuration; its data dir is the working directory.
        config_path: The config file the worker loads; ``~`` is expanded.
        log_file: Standard output and error log; ``~`` is expanded.

    Returns:
        The plist as XML text.
    """
    log = Path(log_file).expanduser().resolve()
    payload = {
        "Label": SERVICE_LABEL,
        "ProgramArguments": [
            sys.executable, "-m", "podscribe", "run", "--config", str(Path(config_path).expanduser().resolve())
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(Path(config.paths["data_dir"]).expanduser().resolve()),
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML).decode("utf-8")


def install_service(
    config: Config,
    *,
    config_path: Path | str,
    log_file: Path | str,
    target: Path | None = None,
    dry_run: bool = False,
) -> Path:
    """Write the worker's LaunchAgent plist.

    Args:
        config: Validated configuration.
        config_path: The config file the worker loads.
        log_file: Standard output and error log.
        target: Plist path; defaults to ``~/Library/LaunchAgents``.
        dry_run: Return the target without writing.

    Returns:
        The plist path.
    """
    path = target or launch_agent_path()
    if dry_run:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_plist(config, config_path=config_path, log_file=log_file), encoding="utf-8")
    return path
