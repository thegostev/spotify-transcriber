"""Tests for reading secrets from the macOS Keychain."""

from types import SimpleNamespace

import pytest

EXPECTED_COMMAND = [
    "security",
    "find-generic-password",
    "-s",
    "ollama-cloud",
    "-a",
    "api-key",
    "-w",
]


def fake_run(returncode=0, stdout="", stderr="", calls=None, raises=None):
    def run(command, **kwargs):
        if calls is not None:
            calls.append(command)
        if raises is not None:
            raise raises
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return run


@pytest.mark.xfail(strict=True, reason="LAG-1046")
def test_get_secret_asks_security_and_strips_newline(monkeypatch):
    from podscribe.keychain import get_secret

    calls = []
    monkeypatch.setattr("podscribe.keychain.subprocess.run", fake_run(stdout="s3cr3t-value\n", calls=calls))

    assert get_secret("ollama-cloud", "api-key") == "s3cr3t-value"
    assert calls == [EXPECTED_COMMAND]


@pytest.mark.xfail(strict=True, reason="LAG-1046")
def test_get_secret_failure_never_leaks_the_value(monkeypatch):
    from podscribe.keychain import KeychainError, get_secret

    monkeypatch.setattr(
        "podscribe.keychain.subprocess.run",
        fake_run(returncode=44, stdout="super-secret", stderr="super-secret"),
    )

    with pytest.raises(KeychainError) as caught:
        get_secret("ollama-cloud", "api-key")

    message = str(caught.value)
    assert "ollama-cloud" in message
    assert "api-key" in message
    assert "super-secret" not in message
    assert caught.value.__cause__ is None


@pytest.mark.xfail(strict=True, reason="LAG-1046")
def test_get_secret_wraps_missing_security_binary(monkeypatch):
    from podscribe.keychain import KeychainError, get_secret

    monkeypatch.setattr(
        "podscribe.keychain.subprocess.run",
        fake_run(raises=FileNotFoundError("security")),
    )

    with pytest.raises(KeychainError, match="ollama-cloud"):
        get_secret("ollama-cloud", "api-key")


@pytest.mark.xfail(strict=True, reason="LAG-1046")
def test_get_secret_rejects_empty_value(monkeypatch):
    from podscribe.keychain import KeychainError, get_secret

    monkeypatch.setattr("podscribe.keychain.subprocess.run", fake_run(stdout="\n"))

    with pytest.raises(KeychainError, match="empty"):
        get_secret("ollama-cloud", "api-key")
