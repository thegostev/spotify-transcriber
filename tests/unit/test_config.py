"""Tests for loading and validating config.yaml."""

from pathlib import Path

import pytest

BASE_CONFIG = """\
paths:
  output_dir: "~/notes/podcasts"
  failure_notes_dir: "~/notes/failures"
  data_dir: "~/.podscribe"
  log_file: "~/.podscribe/podscribe.log"
intake:
  itunes_search_url: "https://itunes.apple.com/search"
  match_window_days: 2
  user_agent: "podscribe/0.0"
speech:
  language: en
  chunk_seconds: null
  plan1:
    engine: ollama
    model: "lfm3-audio"
  plan2:
    engine: mlx-whisper
    model: "mlx-community/whisper-large-v3-turbo"
llm:
  host: "https://ollama.com"
  model: "deepseek-v4.1-flash:cloud"
  api_key:
    keychain_service: "ollama-cloud"
    keychain_account: "api-key"
  timeout_seconds: 300
  retry_backoff_seconds: [30, 60, 120]
  cleanup:
    enabled: true
  summary:
    enabled: true
notifications:
  macos: true
remote:
  transport: rex
  rex_host: "mini"
  rex_session: "podscribe"
  ssh_target: "harald@mac-mini.local"
"""


def write_config(tmp_path: Path, text: str = BASE_CONFIG) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_config_exposes_every_section(tmp_path):
    from podscribe.config import load_config

    config = load_config(write_config(tmp_path))

    assert set(config.paths) == {"output_dir", "failure_notes_dir", "data_dir", "log_file"}
    assert config.intake["match_window_days"] == 2
    assert config.speech["plan1"]["model"] == "lfm3-audio"
    assert config.llm["model"] == "deepseek-v4.1-flash:cloud"
    assert config.notifications["macos"] is True
    assert config.remote["transport"] == "rex"
    assert config.source == tmp_path / "config.yaml"


def test_load_config_expands_tilde_in_paths(tmp_path, monkeypatch):
    from podscribe.config import load_config

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config = load_config(write_config(tmp_path))

    assert config.paths["output_dir"] == str(tmp_path / "home" / "notes" / "podcasts")
    assert config.paths["log_file"] == str(tmp_path / "home" / ".podscribe" / "podscribe.log")


def test_load_config_names_missing_key_and_file(tmp_path):
    from podscribe.config import ConfigError, load_config

    text = BASE_CONFIG.replace("  match_window_days: 2\n", "")
    path = write_config(tmp_path, text)

    with pytest.raises(ConfigError) as caught:
        load_config(path)

    assert "intake.match_window_days" in str(caught.value)
    assert str(path) in str(caught.value)


def test_load_config_rejects_missing_file(tmp_path):
    from podscribe.config import ConfigError, load_config

    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")


def test_load_config_rejects_non_mapping(tmp_path):
    from podscribe.config import ConfigError, load_config

    path = write_config(tmp_path, "- just\n- a list\n")

    with pytest.raises(ConfigError, match="mapping"):
        load_config(path)
